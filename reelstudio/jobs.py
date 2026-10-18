"""The job journal: every generation the studio queues, durable, with its
full request context — the claw-back record for any generated file.

Two halves:

- `record`/`load` — an append-only JSONL under the workspace's `.studio/`
  (one line per lifecycle transition; the last line per id wins). The
  in-memory queue dies with the process; this survives restarts and travels
  with the scene dir.
- `provenance` — file → job id → everything used to make it. The job id is
  stamped where the file lives: a `job:<id>` label in assets.yaml for Qwen
  images, a `job` field in the render manifest for videos and music. For
  images the claw-back goes one deeper: ComfyUI embeds the executed prompt
  graph (prompt, negative, seed, steps, models) in the PNG itself, so the
  file is its own source of truth and the journal never duplicates it.
"""

import json
import struct
import time
from pathlib import Path

from .errors import NotFoundError

JOURNAL_DIR = ".studio"
JOURNAL_NAME = "jobs.jsonl"


def journal_path(config) -> Path:
    return Path(config.workspace) / JOURNAL_DIR / JOURNAL_NAME


def record(config, **entry) -> dict:
    """Append one lifecycle record (`id` required; status transitions are
    separate lines — readers take the last per id)."""
    entry.setdefault("ts", time.time())
    p = journal_path(config)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a") as fh:
        fh.write(json.dumps(entry, sort_keys=True) + "\n")
    return entry


def load(config) -> dict[str, dict]:
    """Every journaled job, last record per id winning."""
    out: dict[str, dict] = {}
    p = journal_path(config)
    if not p.exists():
        return out
    for line in p.read_text().splitlines():
        try:
            e = json.loads(line)
        except ValueError:
            continue  # a torn tail line after a crash — skip it
        if isinstance(e, dict) and "id" in e:
            out[str(e["id"])] = e
    return out


# ---------------------------------------------------------- provenance ----
def png_prompt(path) -> dict | None:
    """The executed prompt graph ComfyUI embeds in a PNG's `prompt` tEXt
    chunk, or None. The file is the single source of truth for what made it —
    the journal deliberately does not copy this."""
    try:
        data = Path(path).read_bytes()
    except OSError:
        return None
    pos = 8
    while pos + 12 <= len(data):
        ln, typ = struct.unpack(">I4s", data[pos:pos + 8])
        typ = typ.decode("latin1")
        if typ == "tEXt":
            key, _, val = data[pos + 8:pos + 8 + ln].partition(b"\x00")
            if key == b"prompt":
                try:
                    return json.loads(val)
                except ValueError:
                    return None
        pos += 12 + ln
        if typ == "IEND":
            break
    return None


_LOADER_KEYS = {"UNETLoader": "unet", "CLIPLoader": "clip",
                "LoraLoaderModelOnly": "lora", "VAELoader": "vae"}


def summarize_prompt(graph: dict | None) -> dict | None:
    """Flatten an embedded ComfyUI graph to the fields a human claws back:
    the text encodes' prompts, the sampler's seed/steps, the loaders' assets,
    the latent size."""
    if not graph:
        return None
    out: dict = {}
    for node in graph.values():
        cls, ins = node.get("class_type", ""), node.get("inputs") or {}
        if cls == "KSampler":
            out["seed"] = ins.get("seed")
            out["steps"] = ins.get("steps")
        elif "TextEncode" in cls:
            for k, v in ins.items():
                if isinstance(v, str):
                    out["negative_prompt" if "negative" in k else "prompt"] = v
        elif cls in _LOADER_KEYS:
            name = _LOADER_KEYS[cls]
            if ins.get(f"{name}_name"):
                out[name] = ins[f"{name}_name"]
        elif cls == "EmptyLatentImage":
            out.update({k: ins[k] for k in ("width", "height") if k in ins})
    return {k: v for k, v in out.items() if v is not None} or None


def _labelled_job(workspace: Path, still_dir, p: Path) -> str | None:
    """The `job:<id>` label reel.py stamps into assets.yaml for every image
    it generates."""
    from .assets import _labels_file, _rel

    key = _rel(p, [workspace] + ([Path(still_dir)] if still_dir else []))
    for rel, labels in _labels_file(workspace).items():
        if rel in (key, p.name):
            tagged = [l for l in labels if l.startswith("job:")]
            if tagged:
                return tagged[0][4:]
    return None


def _manifest_job(reel_dir, p: Path) -> str | None:
    """Scene videos and music carry their job id in the render manifest."""
    from . import manifest as manifest_mod

    m = manifest_mod.load(reel_dir)
    for entry in list(m.get("scenes", {}).values()) + \
            list(m.get("music", {}).values()):
        file = (((entry.get("video") or {}).get("path") or {})
                .get("file")) or ((entry.get("path") or {}).get("file"))
        if file and Path(file).name == p.name and entry.get("job"):
            return entry["job"]
    return None


def provenance(config, path: str) -> dict:
    """Everything used to make one generated file: its job id, the journaled
    job record, and — for images — the prompt embedded in the file itself."""
    from .assets import asset_file

    project = None
    roots = [Path(config.workspace)]
    try:
        from .project import load as load_project
        project = load_project(config)
        roots += [project.meta["still_dir"], project.meta["reel_dir"]]
    except Exception:  # noqa: BLE001 - a broken yaml must not hide provenance
        pass
    p = asset_file(path, roots)
    if not p.is_file():
        raise NotFoundError(f"no such asset: {p.name}")

    still_dir = project.meta["still_dir"] if project else None
    reel_dir = project.meta["reel_dir"] if project else None
    job = _labelled_job(Path(config.workspace), still_dir, p)
    if job is None and reel_dir:
        job = _manifest_job(reel_dir, p)
    return {
        "file": str(p),
        "job": job,
        "record": load(config).get(job) if job else None,
        "embedded": summarize_prompt(png_prompt(p)),
    }
