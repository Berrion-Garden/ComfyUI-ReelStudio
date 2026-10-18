"""Render manifest: what was rendered from what, per scene and music segment.

Lives beside the renders in reel_dir/.reelstudio_manifest.json so a copied
output tree carries its own provenance.
"""

import json
import time
from pathlib import Path

from .assets import AUDIO_EXTS

MANIFEST_NAME = ".reelstudio_manifest.json"


def path(reel_dir: str | Path) -> Path:
    return Path(reel_dir) / MANIFEST_NAME


def load(reel_dir: str | Path) -> dict:
    p = path(reel_dir)
    if not p.exists():
        return {"scenes": {}, "music": {}}
    data = json.loads(p.read_text())
    data.setdefault("scenes", {})
    data.setdefault("music", {})
    return data


def save(reel_dir: str | Path, manifest: dict) -> None:
    p = path(reel_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(manifest, indent=2, sort_keys=True))
    tmp.replace(p)


def record_scene(reel_dir: str, scene_id: str, video_path: str,
                 frames: int, prompt_id: str = "",
                 generation: dict | None = None) -> dict:
    """`generation` caches the scene's collapsed generation input (reel.py's
    merged prompt/anchors) — the artifact staleness diffs against."""
    manifest = load(reel_dir)
    entry = {
        "video": {"kind": "video", "path": {"file": str(Path(video_path).name)}},
        "frames": frames,
        "prompt_id": prompt_id,
        "rendered_at": time.time(),
    }
    if generation is not None:
        entry["generation"] = generation
    manifest["scenes"][scene_id] = entry
    save(reel_dir, manifest)
    return manifest


def record_music(reel_dir: str, name: str, segment_hash: str, audio_path: str) -> dict:
    manifest = load(reel_dir)
    manifest["music"][name] = {
        "hash": segment_hash,
        "path": {"kind": "audio", "file": str(Path(audio_path).name)},
        "rendered_at": time.time(),
    }
    save(reel_dir, manifest)
    return manifest


def music_file(reel_dir: str | Path, name: str) -> str | None:
    """Rendered audio for a music segment, newest wins (audio files only)."""
    hits = [p for p in sorted(Path(reel_dir).glob(f"music_{name}_*"))
            if p.suffix.lower() in AUDIO_EXTS]
    return str(hits[-1]) if hits else None


def deliverable(reel_dir: str | Path, scene_id: str) -> str | None:
    """Newest render wins; freeze outputs sort after plain renders by name."""
    hits = sorted(Path(reel_dir).glob(f"{scene_id}_*.mp4"))
    return str(hits[-1]) if hits else None


def adopt_existing(reel_dir: str | Path, project,
                   scene_id: str | None = None) -> int:
    """Declare the CURRENT deliverables current: every scene with a
    deliverable gets its manifest entry (re)written in the collapse format —
    the current generation input cached as its provenance. Explicit user
    action — it declares 'these renders match this config', never assumed.
    Existing entries adopted under older mechanisms are converted here.
    scene_id narrows the adoption to one scene (the ✓ on its thumbnail)."""
    from . import collapse as collapse_mod

    gen = collapse_mod.current(project)
    manifest = load(reel_dir)
    adopted = 0
    for s in project.scenes:
        sid = s["id"]
        if scene_id is not None and sid != scene_id:
            continue
        d = deliverable(reel_dir, sid)
        if d is None:
            continue
        if sid in manifest["scenes"] and manifest["scenes"][sid].get("generation"):
            continue  # already in the new format; renders are managed, not adopted
        entry = {
            "video": {"kind": "video", "path": {"file": Path(d).name}},
            "frames": s.get("frames", project.default_frames),
            "adopted": True,
        }
        if gen and gen.get(sid):
            entry["generation"] = gen[sid]
        manifest["scenes"][sid] = entry
        adopted += 1
    if adopted:
        save(reel_dir, manifest)
    return adopted
