"""LLM-driven review: the narrative (storyboard.yaml) vs the final cut.

The reviewer LLM reads ONE midpoint frame per rendered segment (extracted
from the assembled deliverable with the same start times the timeline
uses) beside the wired beat's text, and flags anything that does not
match: wrong action or subject, wrong location or wardrobe, mid-action
jump cuts, burnt-in artifacts. The report lands in
`<workspace>/.work/validate_report.json`, written incrementally so the
UI's tab can show progress while the batches run.
"""

import json
from pathlib import Path

from . import narrative as narrative_mod
from . import studio as studio_mod
from . import timeline
from .agent import llm
from .config import Config
from .errors import ConflictError

FRAMES_PER_BATCH = 3

PROMPT = """You are reviewing an anime reel's assembled cut against the \
production narrative. For each segment you get ONE frame from its midpoint \
and the action text the segment was wired to (its beat). Compare them.

Flag a segment (verdict "issue") when the frame does not match the expected \
action, subject, location or wardrobe; when a frame carries burnt-in text, \
watermarks or artifacts; when an on-model character is unrecognizable. Say \
"ok" when the frame is a fair midpoint of the described action — mid-motion \
is NOT an issue. Respond with a compact JSON array, one object per segment, \
exactly: {{"segment": "<id>", "verdict": "ok"|"issue", "note": "<why>"}}.

Segments:
{segments}"""


def report_path(config: Config):
    return config.workspace / ".work" / "validate_report.json"


def load_report(config: Config) -> dict:
    try:
        return json.loads(report_path(config).read_text())
    except (OSError, ValueError):
        return {"state": "idle"}


def _segments(project, root) -> list[dict]:
    """One row per rendered segment: id, beat, the beat's text, start time —
    the wiring the reviewer judges against."""
    view = narrative_mod.view(root)
    texts = {s["id"]: s["text"]
             for a in view["doc"]["acts"]
             for c in a["checkpoints"] for s in c["shots"]}
    starts = timeline.scene_starts(project)
    rows = []
    for i, s in enumerate(project.scenes):
        beat = s.get("beat")
        rows.append({
            "segment": s["id"],
            "beat": beat,
            "expected": texts.get(beat, ""),
            "frame": f"{i}.png",
        })
    return rows


def _extract_frames(project, work) -> bool:
    """One midpoint frame per segment from the final cut; True when all
    extracted. Uses the timeline's own start times — the same numbers the
    assemble used."""
    import subprocess

    final = project.meta.get("final")
    if not final:
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


def _images(config: Config, work, rows: list[dict], batch: list[dict]) -> list:
    from .agent.vision import content_parts, data_url

    roots = [config.workspace]
    images = [data_url(str(work / r["frame"]), roots) for r in batch]
    listing = "\n".join(
        f"- {r['segment']} (beat {r['beat']}): {r['expected']}" for r in batch)
    return [content_parts(PROMPT.format(segments=listing), images)]


async def run(state, project) -> dict:
    """The full review; runs as the server's validate task. The report
    file is the progress channel — rewritten after every batch."""
    config: Config = state.config
    root = studio_mod.resolve(config.workspace).root
    work = config.workspace / ".work" / "validate"
    report = report_path(config)

    final = project.meta.get("final")
    if not (final and Path(final).exists()):
        return _write(report, {"state": "error",
                               "error": "no final cut on disk — assemble first"})
    rows = _segments(project, root)
    if not rows:
        return _write(report, {"state": "error",
                               "error": "no scenes wired — nothing to review"})
    if not _extract_frames(project, work):
        return _write(report, {"state": "error",
                               "error": "frame extraction failed — is the "
                                        "final cut readable?"})

    _write(report, {"state": "running", "total": len(rows), "done": 0,
                    "findings": []})
    findings = []
    for b in range(0, len(rows), FRAMES_PER_BATCH):
        batch = rows[b:b + FRAMES_PER_BATCH]
        try:
            messages = _images(config, work, rows, batch)
            answer = await llm.chat(config, messages, tools=[])
            text = (answer or {}).get("content", "")
            if isinstance(text, list):  # vision answers arrive as parts
                text = " ".join(str(p.get("text", ""))
                                for p in text if isinstance(p, dict))
            parsed = _parse(text, batch)
        except Exception as e:  # noqa: BLE001 — a batch failure is a finding
            parsed = [dict(r, verdict="error", note=str(e)) for r in batch]
        findings += parsed
        _write(report, {"state": "running", "total": len(rows),
                        "done": min(b + FRAMES_PER_BATCH, len(rows)),
                        "findings": findings})
    return _write(report, {"state": "done", "total": len(rows),
                           "done": len(rows), "findings": findings})


def _parse(text: str, batch: list[dict]) -> list[dict]:
    """The reviewer's JSON array, or the raw text as one error row — never
    a silently dropped batch."""
    try:
        start = text.index("[")
        end = text.rindex("]")
        items = json.loads(text[start:end + 1])
        by_id = {r["segment"]: r for r in batch}
        return [dict(by_id[i["segment"]], verdict=i.get("verdict"),
                     note=i.get("note", ""))
                for i in items if isinstance(i, dict)
                and i.get("segment") in by_id]
    except (ValueError, AttributeError, KeyError):
        return [dict(r, verdict="error",
                     note=f"unparsed review: {text[:200]}") for r in batch]


def _write(path, report: dict) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=1))
    return report


# ---------------------------------------------------------- the routes ----

async def start(state) -> dict:
    """Kick off one review run; the report file is the progress channel."""
    if state.validate_task and not state.validate_task.done():
        raise ConflictError(["a validate run is already in progress"])
    state.validate_task = state.run_validate()
    return {"started": True}
