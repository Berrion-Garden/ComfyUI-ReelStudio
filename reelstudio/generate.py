"""The generation seam: every media generator the studio can drive, one entry each.

A Generator owns its whole contract: the agent-facing summary, the arguments
it accepts, target validation (errors teach the caller what would be valid),
and execution. The agent's `generate` tool and the HTTP job routes derive from
this registry, so adding a generator kind is one entry here — never edits in
three places.

Wired: scene (H3 video), music (Music3), assemble (final mix).
Declared, not wired: still / image_edit — anchor stills come from the external
Qwen-Image pipeline into meta.still_dir; a wired executor is the only piece
missing when image generation lands.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .errors import ValidationError
from .project import Project


@dataclass(frozen=True)
class Generator:
    kind: str
    summary: str
    # JSON-schema properties this kind accepts (merged into the tool schema)
    args: dict
    validate: Callable[[Project, dict], list[str]]
    # (project, client, work_dir, target) -> deliverable path; runs in a thread
    execute: Callable[..., str] | None


# ------------------------------------------------------------ validators ---
def _validate_scene(project: Project, args: dict) -> list[str]:
    if args.get("stale"):
        from . import manifest as manifest_mod
        from . import timeline

        wanted = timeline.stale_scenes(
            project, manifest_mod.load(project.meta["reel_dir"]),
            project.meta["reel_dir"])
    else:
        wanted = args.get("scene_ids") or []
    if not wanted:
        raise ValidationError(
            ["nothing to render — pass scene_ids or stale: true"])
    known = project.by_id()
    unknown = [s for s in wanted if s not in known]
    if unknown:
        raise ValidationError([f"unknown scene ids: {unknown}",
                               f"known scenes: {list(known)}"])
    # upstream-first so prev_last junctions resolve in one pass
    return sorted(wanted, key=list(known).index)


def _validate_music(project: Project, args: dict) -> list[str]:
    from .audio import music_segments

    name = args.get("name")
    known = [m["name"] for m in music_segments(project)]
    if name not in known:
        raise ValidationError([f"unknown music segment {name!r}",
                               f"known segments: {known}"])
    return [name]


def _validate_assemble(project: Project, args: dict) -> list[str]:
    flags = project.raw.get("flags", {})
    use_music = bool(args.get("use_music", not flags.get("skip_music", True)))
    return ["music" if use_music else "no-music"]


def _not_wired(kind: str):
    def validate(project: Project, args: dict) -> list[str]:
        raise ValidationError([
            f"{kind} generation is not wired on this install",
            "anchor stills come from the external Qwen-Image pipeline into "
            "meta.still_dir — reference them as still:<name>, or ask the "
            "operator to add stills"])
    return validate


# ------------------------------------------------------------- executors ---
# Execution is delegated to the workspace's reel.py — the single pipeline
# implementation (H3 graphs, freeze post, Music3, the final mix all live
# there; see reelstudio/reel.py). After a successful run the studio vouches
# for the deliverable in the manifest so staleness stays truthful.


def _workspace(work_dir: str):
    from pathlib import Path

    ws = Path(work_dir).resolve()
    if ws.name == ".work":          # the worker passes workspace/.work
        ws = ws.parent
    if not (ws / "reel.py").is_file():
        raise FileNotFoundError(
            f"reel.py not found beside the project yaml ({ws}) — the pipeline "
            "script must live in the workspace")
    return ws


def _record_scene_render(project: Project, target: str) -> str:
    """Point the manifest at the deliverable reel.py just produced."""
    from . import manifest as manifest_mod
    from .timeline import chain_hash, scene_frames

    reel_dir = project.meta["reel_dir"]
    path = manifest_mod.deliverable(reel_dir, target)
    if path is None:
        raise FileNotFoundError(
            f"{target}: reel.py finished but no render landed in {reel_dir}")
    scene = project.by_id()[target]
    upstream = None
    if scene["video"].get("first") == "prev_last":
        prev = project.previous(target)
        prev_file = (manifest_mod.load(reel_dir)["scenes"]
                     .get(prev["id"], {}).get("video", {})
                     .get("path", {}).get("file"))
        if prev_file:
            upstream = (prev["id"], prev_file)
    manifest_mod.record_scene(reel_dir, target, chain_hash(project, scene),
                              path, scene_frames(project, scene),
                              upstream=upstream)
    return path


def _execute_scene(project, client, work_dir, target):
    from . import reel as reel_pipeline

    reel_pipeline.run_sync(_workspace(work_dir), "render", [target])
    return _record_scene_render(project, target)


def _execute_music(project, client, work_dir, target):
    from . import audio as audio_mod
    from . import manifest as manifest_mod
    from . import reel as reel_pipeline

    ws = _workspace(work_dir)
    reel_pipeline.run_sync(ws, "music")
    segment = next(m for m in audio_mod.music_segments(project)
                   if m["name"] == target)
    audio_path = manifest_mod.music_file(project.meta["reel_dir"], target)
    if audio_path is None:
        raise FileNotFoundError(
            f"reel.py music finished but no audio landed in "
            f"{project.meta['reel_dir']}")
    manifest_mod.record_music(project.meta["reel_dir"], target,
                              segment["hash"], audio_path)
    return audio_path


def _execute_assemble(project, client, work_dir, target):
    from . import reel as reel_pipeline

    ws = _workspace(work_dir)
    reel_pipeline.run_sync(
        ws, "assemble", ["--with-music"] if target == "music" else [])
    final = project.meta.get("final")
    if not final or not Path(final).exists():
        raise FileNotFoundError(
            f"reel.py assemble finished but no final at {final}")
    return final


# -------------------------------------------------------------- registry ---
GENERATORS: tuple[Generator, ...] = (
    Generator(
        kind="scene",
        summary="render scene videos through H3 — pass scene_ids (rendered "
                "upstream-first) or stale: true for every stale scene",
        args={
            "scene_ids": {"type": "array", "items": {"type": "string"},
                          "description": "scene ids to render (scene kind)"},
            "stale": {"type": "boolean",
                      "description": "render every stale scene (scene kind)"},
        },
        validate=_validate_scene, execute=_execute_scene),
    Generator(
        kind="music",
        summary="regenerate one anchored Music3 segment — pass its name",
        args={
            "name": {"type": "string",
                     "description": "music segment name (music kind)"},
        },
        validate=_validate_music, execute=_execute_music),
    Generator(
        kind="assemble",
        summary="final production: music bed + bell + concat + mix — "
                "only when the user asks for the final mix",
        args={
            "use_music": {"type": "boolean",
                          "description": "include the music bed (assemble kind)"},
        },
        validate=_validate_assemble, execute=_execute_assemble),
    Generator(
        kind="still",
        summary="NOT WIRED on this install — anchor stills come from the "
                "external Qwen-Image pipeline; ask the operator instead",
        args={}, validate=_not_wired("still"), execute=None),
    Generator(
        kind="image_edit",
        summary="NOT WIRED on this install — anchor stills are edited in the "
                "external Qwen-Image pipeline; ask the operator instead",
        args={}, validate=_not_wired("image_edit"), execute=None),
)

_BY_KIND = {g.kind: g for g in GENERATORS}


def plan(project: Project, kind, args: dict | None) -> list[tuple[str, str]]:
    """Validate a generate request -> [(kind, target)] job specs.
    Raises ValidationError (with teaching problems) on anything unqueueable."""
    g = _BY_KIND.get(kind) if isinstance(kind, str) else None
    if g is None:
        raise ValidationError([f"unknown generator kind {kind!r}",
                               f"known kinds: {[_g.kind for _g in GENERATORS]}"])
    return [(kind, t) for t in g.validate(project, args or {})]


def run_job(project: Project, client, work_dir: str, kind: str, target: str) -> str:
    return _BY_KIND[kind].execute(project, client, work_dir, target)


def tool() -> dict:
    """The agent-facing `generate` function tool, derived from the registry."""
    lines = "\n".join(f"- {g.kind}: {g.summary}" for g in GENERATORS)
    properties: dict = {
        "kind": {"type": "string", "enum": [g.kind for g in GENERATORS],
                 "description": "which generator to run"},
    }
    for g in GENERATORS:
        properties.update(g.args)
    return {"type": "function", "function": {
        "name": "generate",
        "description": "Queue a generation job on the single-GPU worker. Kinds:\n"
                       + lines,
        "parameters": {"type": "object", "properties": properties,
                       "required": ["kind"]}}}
