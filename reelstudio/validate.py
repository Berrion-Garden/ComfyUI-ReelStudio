"""LLM-driven reviews of the narrative against the production, one
reviewer agent per kind. The three kinds:

- prompts: the ORIGINAL beat text vs the FINAL composed prompt per scene
  (verbatim preservation, other beats bleeding in, invented claims)
- entities: the character/location directive blocks vs the narrative
  excerpts that reference them (contradictions, dropped facts)
- frames: one midpoint frame per rendered segment vs its beat's text

Each kind runs as its own server task with its own incremental report
(`.work/validate_report_<kind>.json`) — the review panel polls the
reports and merges them into one view.
"""

import json
from pathlib import Path

from . import collapse as collapse_mod
from . import narrative as narrative_mod
from . import studio as studio_mod
from . import timeline
from .agent import llm
from .agent.vision import content_parts, data_url
from .config import Config
from .errors import ConflictError, ValidationError

KINDS = ("prompts", "entities", "frames")
FRAMES_PER_BATCH = 3

# The reviewer contracts. The JSON example's braces are escaped for
# .format(); every kind responds with one object per row: item/verdict/note.
PROMPTS_PROMPT = """You are auditing the composed end prompts of an anime \
reel against the production narrative. For each scene you get the ORIGINAL \
beat text (the narrative's own words) and the FINAL composed prompt that \
actually reaches the video model — a merge of the style, the location's \
pro text, character directives, the beat's text, and the two named anchor \
stills.

Flag a scene (verdict "issue") when the composed prompt LOSES or REWORDS the \
beat's text; when it carries ANOTHER beat's text; when it ADDS a claim the \
narrative does not make (a fact, a color, a prop, an action). Say "ok" when \
it is a fair merge that preserves the beat's words — anchor naming is \
supposed to be there. Respond with a compact JSON array, one object per \
scene, exactly: {{"item": "<scene id>", "verdict": "ok"|"issue",
"note": "<why>"}}.

Scenes:
{listing}"""

ENTITIES_PROMPT = """You are auditing an anime reel's character and \
location DIRECTIVE blocks against the narrative. For each entry you get \
its YAML directives (what the generator is told about identity, wardrobe, \
age, palette, setting) and the narrative excerpts that reference it.

Flag an entry (verdict "issue") when the directives CONTRADICT a fact the \
narrative states, DROP a fact the narrative relies on (wardrobe the story \
wears, a landmark the story uses), or are SILENT where the narrative needs \
a directive. Say "ok" when they are consistent. Respond with a compact \
JSON array, one object per entry, exactly: {{"item": "<slug>",
"verdict": "ok"|"issue", "note": "<why>"}}.

Entries:
{listing}"""

FRAMES_PROMPT = """You are reviewing an anime reel's assembled cut against \
the production narrative. For each segment you get ONE frame from its \
midpoint and the action text the segment was wired to (its beat). Compare \
them.

Flag a segment (verdict "issue") when the frame does not match the expected \
action, subject, location or wardrobe; when a frame carries burnt-in text, \
watermarks or artifacts; when an on-model character is unrecognizable. Say \
"ok" when the frame is a fair midpoint of the described action — mid-motion \
is NOT an issue. Respond with a compact JSON array, one object per segment, \
exactly: {{"item": "<scene id>", "verdict": "ok"|"issue", "note": "<why>"}}.

Segments:
{listing}"""


def report_path(config: Config, kind: str) -> Path:
    return config.workspace / ".work" / f"validate_report_{kind}.json"


def load_reports(config: Config) -> dict:
    """Every kind's latest report, with an idle default for kinds never run."""
    reports = {}
    for kind in KINDS:
        try:
            reports[kind] = json.loads(report_path(config, kind).read_text())
        except (OSError, ValueError):
            reports[kind] = {"state": "idle"}
    return reports


# ------------------------------------------------------------- row builds --

def _rows_prompts(project, root) -> list[dict]:
    """One row per scene: the beat's original text and the composed prompt
    that actually reaches the model."""
    composed = collapse_mod.current(project)
    if composed is None:
        raise ReviewError(
            "the workspace pipeline cannot compose prompts yet — reel.py "
            "collapse is unavailable")
    view = narrative_mod.view(root)
    texts = {s["id"]: s["text"]
             for a in view["doc"]["acts"]
             for c in a["checkpoints"] for s in c["shots"]}
    rows = []
    for s in project.scenes:
        beat = s.get("beat")
        prompt = (composed.get(s["id"]) or {}).get("prompt", "")
        if not prompt:
            continue  # an unwired/uncomposable scene is the wiring's problem
        rows.append({"item": s["id"], "beat": beat,
                     "original": texts.get(beat, ""), "final": prompt})
    return rows


def _excerpts(project, root, slug: str, key: str) -> str:
    """The narrative excerpts that reference a character/location slug."""
    view = narrative_mod.view(root)
    parts = []
    for a in view["doc"]["acts"]:
        for c in a["checkpoints"]:
            if slug in (c.get(key) or []):
                for s in c["shots"]:
                    parts.append(f"{c['title']} — {s['text']}")
    return "\n\n".join(parts)


def _rows_entities(project, root) -> list[dict]:
    import yaml as _yaml

    rows = []
    for slug, block in (project.raw.get("characters") or {}).items():
        rows.append({"item": slug, "kind": "character",
                     "directives": _yaml.safe_dump(block, sort_keys=False,
                                                   allow_unicode=True),
                     "narrative": _excerpts(project, root, slug,
                                            "characters")})
    for slug, block in (project.raw.get("locations") or {}).items():
        rows.append({"item": slug, "kind": "location",
                     "directives": _yaml.safe_dump(block, sort_keys=False,
                                                   allow_unicode=True),
                     "narrative": _excerpts(project, root, slug,
                                            "locations")})
    return rows


def _rows_frames(project, root) -> list[dict]:
    texts = {s["id"]: s["text"]
             for a in narrative_mod.view(root)["doc"]["acts"]
             for c in a["checkpoints"] for s in c["shots"]}
    starts = timeline.scene_starts(project)
    return [{"item": s["id"], "beat": s.get("beat"),
             "expected": texts.get(s.get("beat"), ""), "frame": f"{i}.png"}
            for i, s in enumerate(project.scenes)]


def _listing(rows: list[dict], keys: list[str]) -> str:
    out = []
    for r in rows:
        line = f"- {r['item']}"
        for k in keys:
            v = r.get(k)
            if v not in (None, ""):
                line += f"\n  {k}: {v}"
        out.append(line)
    return "\n".join(out)


SPECS = {
    "prompts": {"prompt": PROMPTS_PROMPT, "keys": ["original", "final"],
                "rows": _rows_prompts},
    "entities": {"prompt": ENTITIES_PROMPT,
                 "keys": ["kind", "directives", "narrative"],
                 "rows": _rows_entities},
    "frames": {"prompt": FRAMES_PROMPT, "keys": ["beat", "expected"],
               "rows": _rows_frames},
}


class ReviewError(Exception):
    """A kind's data assembly failed — the report carries why."""


# --------------------------------------------------------------- the run --

def _extract_frames(project, work: Path) -> bool:
    """One midpoint frame per segment from the final cut; True when all
    extracted. Uses the timeline's own start times — the same numbers the
    assemble used."""
    import subprocess

    final = project.meta.get("final")
    if not (final and Path(final).exists()):
        return False
    starts = timeline.scene_starts(project)
    work.mkdir(parents=True, exist_ok=True)
    for i, s in enumerate(project.scenes):
        mid = starts[i] + timeline.scene_dur(project, s) / 2
        out = work / f"{i}.png"
        r = subprocess.run(["ffmpeg", "-y", "-v", "error",
                            "-ss", f"{mid:.3f}", "-i", str(final),
                            "-frames:v", "1", str(out)], capture_output=True)
        if r.returncode != 0 or not out.exists():
            return False
    return True


async def run(state, project, kind: str) -> dict:
    """One kind's review as its server task; the report file is the
    progress channel — rewritten after every batch."""
    config: Config = state.config
    root = studio_mod.resolve(config.workspace).root
    spec = SPECS[kind]
    report = report_path(config, kind)
    work = config.workspace / ".work" / "validate"
    try:
        rows = spec["rows"](project, root)
        if kind == "frames" and not _extract_frames(project, work):
            raise ReviewError("frame extraction failed — is the final cut "
                              "on disk and readable?")
    except ReviewError as e:
        return _write(report, {"state": "error", "error": str(e)})

    if not rows:
        return _write(report, {"state": "error",
                               "error": "nothing to review — no rows assembled"})

    def build(batch: list[dict]) -> list:
        listing = _listing(batch, spec["keys"])
        prompt = spec["prompt"].format(listing=listing)
        if kind != "frames":
            return [content_parts(prompt, [])]
        images = [data_url(str(work / r["frame"]), [config.workspace])
                  for r in batch]
        return [content_parts(prompt, images)]

    _write(report, {"state": "running", "kind": kind, "total": len(rows),
                    "done": 0, "findings": []})
    findings = []
    for b in range(0, len(rows), FRAMES_PER_BATCH):
        batch = rows[b:b + FRAMES_PER_BATCH]
        try:
            answer = await llm.chat(config, build(batch), tools=[])
            text = (answer or {}).get("content", "")
            if isinstance(text, list):  # vision answers arrive as parts
                text = " ".join(str(p.get("text", ""))
                                for p in text if isinstance(p, dict))
            parsed = _parse(text, batch)
        except Exception as e:  # noqa: BLE001 — a batch failure is a finding
            parsed = [dict(r, verdict="error", note=str(e)) for r in batch]
        findings += parsed
        _write(report, {"state": "running", "kind": kind, "total": len(rows),
                        "done": min(b + FRAMES_PER_BATCH, len(rows)),
                        "findings": findings})
    return _write(report, {"state": "done", "kind": kind, "total": len(rows),
                           "done": len(rows), "findings": findings})


def _parse(text: str, batch: list[dict]) -> list[dict]:
    """The reviewer's JSON array, or the raw text as one error row — never
    a silently dropped batch."""
    try:
        start = text.index("[")
        end = text.rindex("]")
        items = json.loads(text[start:end + 1])
        by_id = {r["item"]: r for r in batch}
        return [dict(by_id[i["item"]], verdict=i.get("verdict"),
                     note=i.get("note", ""))
                for i in items if isinstance(i, dict)
                and i.get("item") in by_id]
    except (ValueError, AttributeError, KeyError):
        return [dict(r, verdict="error",
                     note=f"unparsed review: {text[:200]}") for r in batch]


def _write(path: Path, report: dict) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=1))
    return report


# ---------------------------------------------------------- the routes ----

async def start(state, kinds: list[str]) -> dict:
    """Kick off one reviewer agent per selected kind; already-running kinds
    are reported back, not double-started."""
    unknown = [k for k in kinds if k not in KINDS]
    if unknown:
        raise ValidationError([f"unknown review kinds: {unknown}"])
    if not kinds:
        raise ValidationError(["select at least one kind of validation"])
    started, already = [], []
    for kind in kinds:
        task = state.validate_tasks.get(kind)
        if task and not task.done():
            already.append(kind)
            continue
        state.validate_tasks[kind] = state.run_validate(kind)
        started.append(kind)
    return {"started": started, "already_running": already}
