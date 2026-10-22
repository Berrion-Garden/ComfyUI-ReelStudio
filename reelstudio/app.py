"""Reel Studio web app: routes, job queue, artifact serving.

create_app() builds a standalone aiohttp application — that is what tests run
against the isolated endpoint (127.0.0.1:8288) and what server.py mounts onto
ComfyUI's PromptServer in production. One handler set, one adapter.
"""

import asyncio
import dataclasses
import json
import os
import re
import subprocess
import urllib.parse
import uuid
import time
import yaml
from pathlib import Path

from aiohttp import web

from . import manifest as manifest_mod
from . import narrative as narrative_mod
from . import assets as assets_mod
from . import generate, jobs as jobs_mod, studio as studio_mod, timeline
from . import audio as audio_mod
from . import reel as reel_pipeline
from . import ytdlp as ytdlp_mod
from .agent.loop import run as agent_run
from .agent.tools import ToolBox
from .config import Config
from .errors import (ConflictError, ForbiddenError, NotFoundError,
                     ReelStudioError, ValidationError)
from .project import load as load_project
from .readmodel import asset_view, project_view

API = "/reelstudio/api"


class RenderJob:
    def __init__(self, kind: str, target: str, args: dict | None = None):
        self.id = uuid.uuid4().hex[:12]
        self.kind = kind          # scene | music | assemble | sheet | still | image_edit
        self.target = target
        self.args = dict(args or {})  # the request context the job ran with
        self.status = "queued"    # queued | running | done | error
        self.error: str | None = None
        self.result: str | None = None
        self.seed: str | None = None
        self.ts = time.time()
        self.config: Config | None = None  # set by enqueue: journal target

    def view(self) -> dict:
        return {"id": self.id, "kind": self.kind, "target": self.target,
                "args": self.args, "status": self.status, "error": self.error,
                "result": self.result, "seed": self.seed, "ts": self.ts}


class ReelStudio:
    """App state: config, the loaded project, and the render queue."""

    def __init__(self, config: Config):
        self.config = config
        self.jobs: dict[str, RenderJob] = {}
        self._queue: asyncio.Queue[RenderJob] = asyncio.Queue()
        self._worker: asyncio.Task | None = None

    # ------------------------------------------------------------ project --
    def project(self):
        from .project import load_cached
        return load_cached(self.config)

    def reopen(self, workspace: Path) -> None:
        """Point the app at another scene dir. project() memoizes on the
        yaml's mtime, so this rebinding is the whole scene switch."""
        self.config = dataclasses.replace(self.config, workspace=Path(workspace))

    # -------------------------------------------------------------- jobs ---
    async def start(self, app):
        self._worker = asyncio.create_task(self._work(), name="reelstudio-worker")

    async def close(self, app):
        if self._worker:
            self._worker.cancel()

    def enqueue(self, kind: str, target: str, args: dict | None = None) -> RenderJob:
        job = RenderJob(kind, target, args)
        job.config = self.config  # journal where it was queued, not where it ends
        self.jobs[job.id] = job
        jobs_mod.record(self.config, id=job.id, kind=kind, target=target,
                        args=job.args, status="queued", ts=job.ts)
        self._queue.put_nowait(job)
        return job

    async def _work(self):
        # one render at a time: the GPU node is a single resource
        while True:
            job = await self._queue.get()
            job.status = "running"
            jobs_mod.record(job.config, id=job.id, status="running")
            try:
                project = load_project(job.config)
                result, extra = await asyncio.to_thread(
                    generate.run_job, project, None,
                    job.config.workspace.as_posix() + "/.work",
                    job.kind, job.target, job.id)
            except Exception as e:  # noqa: BLE001 - job errors surface in the UI
                job.status = "error"
                job.error = str(e)
                jobs_mod.record(job.config, id=job.id, status="error",
                                error=job.error)
            else:
                job.status = "done"
                job.result = result
                job.seed = extra.get("seed")
                jobs_mod.record(job.config, id=job.id, status="done",
                                result=job.result, seed=job.seed)
            self._queue.task_done()


# ------------------------------------------------------------- handlers ----
STATE_KEY = web.AppKey("reelstudio", ReelStudio)
def _state(request: web.Request) -> ReelStudio:
    return request.app[STATE_KEY]


def _json_error(e: ReelStudioError):
    status = 404 if isinstance(e, NotFoundError) else 400
    if isinstance(e, ForbiddenError):
        status = 403
    if isinstance(e, ConflictError):
        status = 409
    body = {"error": str(e)}
    if isinstance(e, ValidationError):
        body["problems"] = e.problems
    return web.json_response(body, status=status)


async def get_project(request: web.Request) -> web.Response:
    try:
        state = _state(request)
        # the read model hashes anchor stills (cold) — keep it off the
        # event loop so a slow first read cannot starve every other route
        view = await asyncio.get_running_loop().run_in_executor(
            None, project_view, state)
        return web.json_response(view)
    except ValidationError as e:
        return _json_error(e)


async def get_yaml(request: web.Request) -> web.Response:
    state = _state(request)
    return web.json_response({"text": state.config.yaml_path.read_text()})


async def put_yaml(request: web.Request) -> web.Response:
    state = _state(request)
    body = await request.json()
    text = body.get("text")
    if not isinstance(text, str):
        return web.json_response({"error": "body must be {text: yaml}"}, status=400)
    project = state.project()
    try:
        warnings = project.save(text)
    except ValidationError as e:
        return _json_error(e)
    return web.json_response({"saved": True, "warnings": warnings})


async def post_render(request: web.Request) -> web.Response:
    state = _state(request)
    body = await request.json()
    specs = generate.plan(state.project(), "scene", body)
    jobs = [state.enqueue(kind, target, body) for kind, target in specs]
    return web.json_response({"jobs": [j.view() for j in jobs]})


async def post_music(request: web.Request) -> web.Response:
    state = _state(request)
    body = await request.json()
    specs = generate.plan(state.project(), "music",
                          {"name": body.get("name")})
    jobs = [state.enqueue(kind, target, body) for kind, target in specs]
    return web.json_response({"jobs": [j.view() for j in jobs]})


async def post_assemble(request: web.Request) -> web.Response:
    state = _state(request)
    body = await request.json() if request.can_read_body else {}
    specs = generate.plan(state.project(), "assemble", body)
    jobs = [state.enqueue(kind, target, body) for kind, target in specs]
    return web.json_response({"jobs": [j.view() for j in jobs]})


async def get_jobs(request: web.Request) -> web.Response:
    state = _state(request)
    live = {j.id: j.view() for j in state.jobs.values()}
    # the journal fills in every past run — restarts don't erase history
    history = [e for i, e in jobs_mod.load(state.config).items()
               if i not in live]
    jobs = sorted(list(live.values()) + history,
                  key=lambda j: j.get("ts", 0), reverse=True)
    return web.json_response({"jobs": jobs})


async def get_provenance(request: web.Request) -> web.Response:
    """The claw-back: one generated file → its job, its request context, and
    (for images) the prompt graph embedded in the file itself."""
    state = _state(request)
    return web.json_response(
        jobs_mod.provenance(state.config, request.query.get("path", "")))


async def get_scene_artifact(request: web.Request) -> web.Response:
    state = _state(request)
    project = state.project()
    sid = request.match_info["scene_id"]
    kind = request.match_info["kind"]
    scene = project.scene(sid)
    if scene is None:
        raise NotFoundError(f"unknown scene {sid!r}")

    if kind == "video":
        file = manifest_mod.deliverable(project.meta["reel_dir"], sid)
        if file is None:
            raise NotFoundError(f"scene {sid!r} has no render")
        return web.FileResponse(Path(file))

    if kind == "sfx":
        split = audio_mod.split_path(project, sid)
        if not split.is_file():
            raise NotFoundError(
                f"scene {sid!r} has no audio split (reel.py sfx {sid})")
        return web.FileResponse(split)

    if kind in ("thumb_first", "thumb_last"):
        anchor = scene["video"].get("first" if kind == "thumb_first" else "last")
        resolved = timeline.resolve_anchor(project, anchor)
        if resolved["kind"] == "none":
            raise NotFoundError(f"scene {sid!r} has no {kind[6:]} anchor")
        if resolved["kind"] == "prev_last":
            prev = project.previous(sid)
            src = manifest_mod.deliverable(project.meta["reel_dir"], prev["id"])
            if src is None:
                raise NotFoundError(f"upstream {prev['id']} has no render")
            cache = Path(state.config.workspace) / ".work" / "thumbs"
            cache.mkdir(parents=True, exist_ok=True)
            png = cache / f"{prev['id']}.png"
            if not png.exists() or Path(src).stat().st_mtime > png.stat().st_mtime:
                subprocess.run(
                    ["/usr/bin/ffmpeg", "-y", "-v", "error", "-sseof", "-0.05",
                     "-i", str(src), "-frames:v", "1", str(png)],
                    check=True)
            return web.FileResponse(png)
        if resolved["kind"] == "still":
            path = resolved.get("path")
            if not path or not Path(path).exists():
                raise NotFoundError(f"still file for {sid!r} missing")
            return web.FileResponse(Path(path))
        return web.FileResponse(Path(resolved["path"]))

    raise NotFoundError(f"unknown artifact kind {kind!r}")


async def get_music_artifact(request: web.Request) -> web.Response:
    """Rendered audio for a music segment (range-capable FileResponse)."""
    state = _state(request)
    project = state.project()
    file = manifest_mod.music_file(project.meta["reel_dir"],
                                   request.match_info["name"])
    if file is None:
        raise NotFoundError("segment not rendered yet")
    return web.FileResponse(Path(file))


async def get_audio_artifact(request: web.Request) -> web.Response:
    """An `audio:` track's source file, as declared in reel.yaml.

    The index — not a client-supplied path — selects the file, so the
    operator's music library stays reachable without widening the asset roots.
    """
    state = _state(request)
    project = state.project()
    try:
        t = audio_mod.track(project, int(request.match_info["index"]))
    except ValueError:
        raise NotFoundError("no such audio track")
    file = Path(t["file"]).expanduser()
    if not file.is_file():
        raise NotFoundError("audio file missing")
    return web.FileResponse(file)


async def get_audio_peaks(request: web.Request) -> web.Response:
    """Waveform envelope for the audio graph lane."""
    state = _state(request)
    project = state.project()
    try:
        index = int(request.match_info["index"])
    except ValueError:
        raise NotFoundError("no such audio track")
    try:
        buckets = min(int(request.query.get("buckets", "600")), 4000)
    except ValueError:
        buckets = 600
    peaks = await asyncio.to_thread(audio_mod.peaks, project, index, buckets)
    return web.json_response({"peaks": peaks})


async def put_audio_track(request: web.Request) -> web.Response:
    """Update one track's timestamp note (at/seek/gain/fades) in reel.yaml."""
    state = _state(request)
    project = state.project()
    body = await request.json()
    try:
        index = int(request.match_info["index"])
    except ValueError:
        raise NotFoundError("no such audio track")
    try:
        t = audio_mod.update_track(project, state.config, index, body)
    except ValueError:
        raise NotFoundError("no such audio track")
    return web.json_response(t)


async def post_audio_import(request: web.Request) -> web.Response:
    """Grab a reference track off the web (YouTube, …) into the scene's
    audio/ library: {url, name?}. The file is an ordinary asset afterwards —
    an `audio:` entry in reel.yaml puts it on the timeline."""
    state = _state(request)
    body = await request.json()
    url = body.get("url")
    name = body.get("name")
    if name is not None and not isinstance(name, str):
        raise ValidationError(["name must be a string"])
    path = await asyncio.to_thread(
        ytdlp_mod.grab, Path(state.config.workspace), str(url or ""), name)
    return web.json_response({
        "path": str(path.relative_to(Path(state.config.workspace))),
        "file": path.name})


async def get_sfx_board(request: web.Request) -> web.Response:
    """Per-scene sound-effects facts: the soundscape prompt, the bell asset,
    and the split audio (waveform peaks optional via ?peaks=<buckets>)."""
    state = _state(request)
    project = state.project()
    try:
        buckets = max(0, int(request.query.get("peaks", "0")))
    except ValueError:
        buckets = 0
    items = []
    for s in project.scenes:
        se = s.get("sound_effects") or {}
        sid = s["id"]
        split = audio_mod.split_path(project, sid)
        item = {
            "id": sid,
            "soundscape": str(se.get("soundscape") or ""),
            "bell": se.get("bell"),
            "bell_at": se.get("bell_at"),
            "split": f"{API}/scene/{sid}/artifact/sfx" if split.is_file() else None,
            "peaks": None,
            "assets": [],
        }
        for ev in audio_mod.sfx_events(project, sid):
            item["assets"].append({
                "asset": ev["asset"], "at": ev["at"], "gain": ev["gain"],
                "url": (f"{API}/asset/file?path=sfx/{ev['file']}"
                        if ev["file"] else None),
            })
        if buckets and item["split"]:
            item["peaks"] = await asyncio.to_thread(
                audio_mod.peaks_for_path, split, buckets)
        items.append(item)
    return web.json_response({"scenes": items})


async def post_sfx_event(request: web.Request) -> web.Response:
    """Place a sound-effect asset on the timeline: {scene_id, asset, at, gain}."""
    state = _state(request)
    body = await request.json()
    return web.json_response(audio_mod.place_sfx_event(
        state.project(), state.config, str(body.get("scene_id", "")), body))


async def delete_sfx_event(request: web.Request) -> web.Response:
    """Remove a placed one-shot: {scene_id, index}."""
    state = _state(request)
    body = await request.json()
    try:
        index = int(body.get("index"))
    except (TypeError, ValueError):
        raise ValidationError(["index must be an integer"])
    return web.json_response(audio_mod.remove_sfx_event(
        state.project(), state.config, str(body.get("scene_id", "")), index))


async def get_bell_artifact(request: web.Request) -> web.Response:
    """The synth bell sample, rendered by reel.py (one bell implementation)."""
    state = _state(request)
    project = state.project()
    cache = Path(project.meta.get("work", "")) / "bell.wav"
    if not cache.is_file():
        await asyncio.to_thread(
            reel_pipeline.run_sync,
            Path(state.config.workspace), "bell", [str(cache)])
    return web.FileResponse(cache)


async def get_assets(request: web.Request) -> web.Response:
    state = _state(request)
    data = asset_view(state)
    for group in data["groups"].values():
        for a in group:
            a["url"] = f"{API}/asset/file?path={urllib.parse.quote(a['path'], safe='')}"
    return web.json_response(data)


async def get_asset_file(request: web.Request) -> web.Response:
    state = _state(request)
    project = state.project()
    target = assets_mod.asset_file(request.query.get("path", ""), [
        state.config.workspace, project.meta["still_dir"], project.meta["reel_dir"],
    ])
    if not target.is_file():
        raise NotFoundError(f"no such asset: {target.name}")
    return web.FileResponse(target)


async def put_asset_labels(request: web.Request) -> web.Response:
    """Rewrite one asset's declared labels: {path, labels: [..]}. Approving
    (removing `non-verified` from a generated character still) also records
    its seed into reel.yaml `characters.<slug>.seeds:` — approved seeds are
    the base for future pose runs."""
    state = _state(request)
    body = await request.json()
    labels = body.get("labels")
    if not isinstance(labels, list) or not all(isinstance(x, str) for x in labels):
        raise ValidationError(["labels must be a list of strings"])
    project = state.project()
    result = await asyncio.to_thread(
        assets_mod.set_labels, state.config.workspace,
        project.meta["still_dir"], str(body.get("path", "")), labels)
    if "non-verified" not in labels and labels:
        await asyncio.to_thread(_record_approved_seed, state, body.get("path"))
    return web.json_response(result)


def _record_approved_seed(state, path) -> None:
    """An approved generation's seed joins the yaml `characters.<slug>.seeds:`
    ladder — the next pose run starts from what worked (best effort: a
    missing seed or slug is skipped, never blocks the approval)."""
    p = Path(str(path))
    ws = Path(state.config.workspace)
    labels = assets_mod._labels_file(ws).get(
        assets_mod._rel(p, [ws, Path(state.project().meta["still_dir"])]), [])
    slug = next((lab.split(":", 1)[1] for lab in labels
                 if lab.startswith("char:")), None)
    if not slug:
        return
    seed = None
    try:
        from PIL import Image
        with Image.open(p) as im:
            meta = im.info.get("prompt")  # ComfyUI embeds the graph JSON
            if meta:
                for node in json.loads(meta).values():
                    if node.get("class_type") == "KSampler":
                        seed = node.get("inputs", {}).get("seed")
                        break
    except Exception:  # noqa: BLE001 - provenance is best-effort
        return
    if seed is None:
        return
    try:
        from ruamel.yaml import YAML
        ry = YAML()
        ry.preserve_quotes = True
        ry.width = 4096
        doc = ry.load(state.config.yaml_path) or {}
        chars = doc.setdefault("characters", {}).setdefault(slug, {})
        ladder = [int(s) for s in (chars.get("seeds") or [])]
        if seed in ladder:
            return
        chars["seeds"] = sorted(ladder + [int(seed)])
        with open(state.config.yaml_path, "w") as fh:
            ry.dump(doc, fh)
    except Exception:  # noqa: BLE001 - a bad yaml must not block approval
        return


def _anchored_stills(project) -> dict[str, list[str]]:
    """Resolved still path -> the scene ids that anchor it: a scene's
    video.first/last `still:<slug>` pins that file to the timeline."""
    anchored: dict[str, list[str]] = {}
    for scene in project.scenes:
        for key in ("first", "last"):
            ref = scene.get("video", {}).get(key)
            if isinstance(ref, str) and ref.startswith("still:"):
                p = project.still_path(ref.split(":", 1)[1])
                if p is not None:
                    anchored.setdefault(str(p.resolve()), []).append(scene["id"])
    return anchored


async def delete_asset(request: web.Request) -> web.Response:
    """The operator's ✗ or ⋯ menu: delete the file and its label entry.
    A still a scene anchors on is not deletable — unanchor it first."""
    state = _state(request)
    body = await request.json()
    project = state.project()
    target = assets_mod.asset_file(str(body.get("path", "")), [
        state.config.workspace, project.meta["still_dir"]])
    index = assets_mod.index_assets(state.config.workspace, project)
    item = next((a for items in index["groups"].values() for a in items
                 if a["path"] == str(target)), None)
    if item is None:
        raise NotFoundError("no such asset")
    tied = _anchored_stills(project).get(str(target.resolve()))
    if tied:
        raise ConflictError("tied to scene start/end: " + ", ".join(tied))
    await asyncio.to_thread(target.unlink)
    await asyncio.to_thread(
        assets_mod.set_labels, state.config.workspace,
        project.meta["still_dir"], str(target), [])
    return web.json_response({"deleted": target.name})


async def get_final(request: web.Request) -> web.Response:
    state = _state(request)
    final = state.project().meta.get("final")
    if not final or not Path(final).exists():
        raise NotFoundError("no final production yet — run assemble")
    return web.FileResponse(Path(final))


async def post_agent_chat(request: web.Request) -> web.StreamResponse:
    state = _state(request)
    body = await request.json()
    history = body.get("history") or []
    user_text = (body.get("message") or "").strip()
    if not user_text:
        return web.json_response({"error": "message required"}, status=400)
    history = [*history, {"role": "user", "content": user_text}]
    sel = body.get("selected")
    # one asset (legacy shape) or several — shift-click multi-select
    if isinstance(sel, dict):
        selected: list[dict] | None = [sel]
    elif isinstance(sel, list):
        selected = [s for s in sel if isinstance(s, dict)] or None
    else:
        selected = None

    # the agent is visual, but nothing rides along by default: the
    # selection's pictures are delivered through currently_selected when the
    # agent references it. attach_selection is the operator's explicit
    # "send it with this message" toggle.
    images = []
    if selected and body.get("attach_selection"):
        primary_path = str(selected[-1].get("path", ""))
        if Path(primary_path).suffix.lower() in \
                {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
            images.append(primary_path)

    resp = web.StreamResponse(headers={
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
    })
    await resp.prepare(request)
    try:
        async for event in agent_run(state.config, history,
                                     ToolBox(state, selected=selected),
                                     images=images):
            await resp.write(f"data: {json.dumps(event, ensure_ascii=False)}\n\n".encode())
    except Exception as e:  # noqa: BLE001 - stream the failure to the UI
        await resp.write(f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n".encode())
        await resp.write(b"data: {\"type\": \"done\"}\n\n")
    await resp.write_eof()
    return resp


# --------------------------------------------------------------- studio ----
def _studio_view(state: ReelStudio) -> dict:
    return studio_mod.view_of(state.config.workspace)


async def get_studio(request: web.Request) -> web.Response:
    return web.json_response(_studio_view(_state(request)))


async def post_studio_save(request: web.Request) -> web.Response:
    """Save the reference to the current scene: on an implicit workspace
    this performs the studio migration; on a saved studio it persists."""
    state = _state(request)
    body = await request.json()
    slug = str(body.get("slug") or
               studio_mod.resolve(state.config.workspace).current)
    scene = studio_mod.save_as(state.config.workspace, slug,
                               body.get("title"))
    state.reopen(scene)
    return web.json_response(_studio_view(state))


async def post_studio_open(request: web.Request) -> web.Response:
    state = _state(request)
    body = await request.json()
    scene = studio_mod.open_scene(state.config.workspace,
                                  str(body.get("slug", "")))
    state.reopen(scene)
    return web.json_response(_studio_view(state))


async def post_studio_scenes(request: web.Request) -> web.Response:
    """New scene: (implicitly saving an implicit workspace first), scaffold,
    switch to it."""
    state = _state(request)
    body = await request.json()
    ws = state.config.workspace
    if not studio_mod.resolve(ws).saved:
        state.reopen(studio_mod.save_as(ws, studio_mod.resolve(ws).current, None))
    project = state.project()
    scene = studio_mod.create_scene(state.config.workspace,
                                    str(body.get("title", "")),
                                    project.meta)
    state.reopen(scene)
    imp = body.get("import") or {}
    if imp.get("from"):
        studio_mod.import_assets(state.config.workspace,
                                 str(imp["from"]),
                                 imp.get("characters") or (),
                                 imp.get("backgrounds") or ())
    return web.json_response(_studio_view(state))


async def get_narrative(request: web.Request) -> web.Response:
    state = _state(request)
    root = studio_mod.resolve(state.config.workspace).root
    return web.json_response(narrative_mod.view(root))


async def put_narrative(request: web.Request) -> web.Response:
    state = _state(request)
    body = await request.json()
    doc = body.get("doc")
    if isinstance(doc, dict):
        # the UI edits the parsed document; the server owns the YAML dump
        text = yaml.safe_dump(doc, sort_keys=False, allow_unicode=True,
                              width=76)
    else:
        text = body.get("text")
    if not isinstance(text, str):
        return web.json_response(
            {"error": "body must be {doc: {style, acts}} or {text: yaml}"},
            status=400)
    root = studio_mod.resolve(state.config.workspace).root
    try:
        narrative_mod.save(root, text)
    except ValidationError as e:
        return _json_error(e)
    return web.json_response({"saved": True})


async def post_studio_import(request: web.Request) -> web.Response:
    """Copy character/location pools from another scene into the current
    one; the optional `as` renames a single imported pool."""
    state = _state(request)
    body = await request.json()
    out = studio_mod.import_assets(state.config.workspace,
                                   str(body.get("from", "")),
                                   body.get("characters") or (),
                                   body.get("backgrounds") or (),
                                   body.get("as"))
    return web.json_response(out)


# -------------------------------------------------------------- upload -----
UPLOAD_EXTS = {
    "characters": {".png", ".jpg", ".jpeg", ".webp"},
    "backgrounds": {".png", ".jpg", ".jpeg", ".webp"},
    "images": {".png", ".jpg", ".jpeg", ".webp"},
    "audio": {".mp3", ".wav", ".ogg", ".flac", ".m4a"},
    "sfx": {".mp3", ".wav", ".ogg", ".flac", ".m4a"},
}
UPLOAD_MAX = 200 * 1024 * 1024


async def post_upload(request: web.Request) -> web.Response:
    """The studio's upload anchors (paperclip, section +, drag-and-drop):
    one multipart file into a workspace library dir. The dir's first path
    segment decides the extension allowlist; the asset index picks the file
    up on the next refresh — nothing hand-indexed."""
    state = _state(request)
    qdir = request.query.get("dir", "images").strip("/")
    root = Path(state.config.workspace).resolve()
    target_dir = (root / qdir).resolve()
    if not target_dir.is_relative_to(root) or target_dir == root:
        raise ForbiddenError("upload dir escapes the workspace")
    top = target_dir.relative_to(root).parts[0]
    allowed = UPLOAD_EXTS.get(top)
    if allowed is None:
        raise ValidationError(
            [f"uploads land in one of: {sorted(UPLOAD_EXTS)}"])

    reader = await request.multipart()
    field = await reader.next()
    if field is None or field.name != "file":
        return web.json_response(
            {"error": "expected a multipart 'file' field"}, status=400)
    orig = Path(field.filename or "upload").name  # basename only
    stem, ext = os.path.splitext(orig)
    if ext.lower() not in allowed:
        raise ValidationError(
            [f"{ext or '(no extension)'} does not belong in {top}/",
             f"allowed there: {sorted(allowed)}"])
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", stem) or "upload"
    final, n = f"{safe}{ext.lower()}", 1
    while (target_dir / final).exists():
        final = f"{safe}-{n}{ext.lower()}"
        n += 1
    target_dir.mkdir(parents=True, exist_ok=True)
    size = 0
    too_big = False
    with open(target_dir / final, "wb") as fh:
        while chunk := await field.read_chunk(1 << 16):
            size += len(chunk)
            if size > UPLOAD_MAX:
                too_big = True
                break
            fh.write(chunk)
    if too_big:
        (target_dir / final).unlink()
        raise ValidationError(["file exceeds the 200MB upload cap"])
    return web.json_response({
        "path": str((target_dir / final).relative_to(root)),
        "file": final})


async def post_manifest_adopt(request: web.Request) -> web.Response:
    """Declare pre-app renders current so staleness starts from truth. With
    {scene_id}, adopts just that scene — the ✓ on its timeline thumbnail."""
    state = _state(request)
    body = await request.json() if request.can_read_body else {}
    project = state.project()
    adopted = manifest_mod.adopt_existing(
        project.meta["reel_dir"], project,
        str(body.get("scene_id")) if body.get("scene_id") else None)
    return web.json_response({"adopted": adopted})


def create_app(config: Config) -> web.Application:
    app = web.Application()

    @web.middleware
    async def error_middleware(request: web.Request, handler):
        try:
            return await handler(request)
        except ReelStudioError as e:
            return _json_error(e)
        except web.HTTPException:
            raise

    app.middlewares.append(error_middleware)
    # a workspace pointing at the studio ROOT resolves to the current
    # scene's dir — the project (reel.yaml) lives in the scene, never at
    # the root. open/save rebind from here.
    resolved = studio_mod.resolve(config.workspace)
    if resolved.saved:
        config = dataclasses.replace(config, workspace=resolved.scene_dir)
    state = ReelStudio(config)
    app[STATE_KEY] = state
    app.router.add_get(f"{API}/project", get_project)
    app.router.add_get(f"{API}/yaml", get_yaml)
    app.router.add_put(f"{API}/yaml", put_yaml)
    app.router.add_post(f"{API}/render", post_render)
    app.router.add_post(f"{API}/music", post_music)
    app.router.add_post(f"{API}/assemble", post_assemble)
    app.router.add_get(f"{API}/jobs", get_jobs)
    app.router.add_get(f"{API}/provenance", get_provenance)
    app.router.add_get(f"{API}/final", get_final)
    app.router.add_get(f"{API}/assets", get_assets)
    app.router.add_put(f"{API}/assets/labels", put_asset_labels)
    app.router.add_delete(f"{API}/asset", delete_asset)
    app.router.add_get(f"{API}/asset/file", get_asset_file)
    app.router.add_get(f"{API}/music/{{name}}/artifact", get_music_artifact)
    app.router.add_get(f"{API}/audio/{{index}}/artifact", get_audio_artifact)
    app.router.add_get(f"{API}/audio/{{index}}/peaks", get_audio_peaks)
    app.router.add_put(f"{API}/audio/{{index}}", put_audio_track)
    app.router.add_post(f"{API}/audio/import", post_audio_import)
    app.router.add_get(f"{API}/bell/artifact", get_bell_artifact)
    app.router.add_get(f"{API}/sfx/board", get_sfx_board)
    app.router.add_post(f"{API}/sfx/board", post_sfx_event)
    app.router.add_delete(f"{API}/sfx/board", delete_sfx_event)
    app.router.add_post(f"{API}/manifest/adopt", post_manifest_adopt)
    app.router.add_get(f"{API}/studio", get_studio)
    app.router.add_get(f"{API}/narrative", get_narrative)
    app.router.add_put(f"{API}/narrative", put_narrative)
    app.router.add_post(f"{API}/studio/save", post_studio_save)
    app.router.add_post(f"{API}/studio/open", post_studio_open)
    app.router.add_post(f"{API}/studio/scenes", post_studio_scenes)
    app.router.add_post(f"{API}/studio/import", post_studio_import)
    app.router.add_post(f"{API}/upload", post_upload)
    app.router.add_get(f"{API}/scene/{{scene_id}}/artifact/{{kind}}", get_scene_artifact)
    app.router.add_post(f"{API}/agent/chat", post_agent_chat)
    app.on_startup.append(state.start)
    app.on_cleanup.append(state.close)
    return app
