"""Audio tracks — the real-file overlays (`audio:` in reel.yaml).

One owner for the audio-track facts every other consumer points at: span
derivation from the absolute `at` timestamp + fades envelope, waveform peaks
for the audio graph, and comment-preserving edits back into the yaml.
"""

import subprocess
from pathlib import Path

from .errors import NotFoundError, ValidationError
from .timeline import SECONDS_DIGITS, scene_starts, total_dur

FF = "/usr/bin/ffmpeg"


def music_segments(project) -> list[dict]:
    """Scene-anchored Music3 segments: start at their scene, run to the next
    anchor (or reel end). Each carries a hash for staleness tracking."""
    import hashlib

    starts = scene_starts(project)
    total = total_dur(project)
    anchors = [(i, s["music"]) for i, s in enumerate(project.scenes)
               if isinstance(s.get("music"), dict)]
    out = []
    for k, (idx, m) in enumerate(anchors):
        start = starts[idx]
        end = starts[anchors[k + 1][0]] if k + 1 < len(anchors) else total
        seg = {
            "name": m["name"],
            "caption": m["caption"].format(**project.aliases),
            "start": round(start, SECONDS_DIGITS),
            "dur": round(end - start, SECONDS_DIGITS),
            "gain": m.get("gain", 1.0),
        }
        blob = f"{seg['caption']}|{seg['start']}|{seg['dur']}|{seg['gain']}"
        seg["hash"] = hashlib.sha256(blob.encode()).hexdigest()[:16]
        out.append(seg)
    return out


def audio_tracks(project) -> list[dict]:
    """The `audio:` array resolved to playable spans: start = the absolute
    `at` timestamp, end = the last fades keyframe (or the reel end)."""
    total = total_dur(project)
    out = []
    for i, c in enumerate(project.raw.get("audio") or []):
        start = float(c.get("at", 0.0))
        fades = [[float(t), float(v)] for t, v in (c.get("fades") or [])]
        end = fades[-1][0] if fades else total
        name = c.get("name") or Path(c["file"]).stem
        out.append({
            "index": i,
            "name": name,
            "file": c["file"],
            "start": round(start, SECONDS_DIGITS),
            "dur": round(end - start, SECONDS_DIGITS),
            "gain": float(c.get("gain", 1.0)),
            "seek": float(c.get("seek", 0.0)),
            "fades": fades,
        })
    return out


def track(project, index: int) -> dict:
    tracks = audio_tracks(project)
    if not 0 <= index < len(tracks):
        raise NotFoundError(f"no such audio track: {index}")
    return tracks[index]


def split_path(project, scene_id: str) -> Path:
    """A scene's split audio ({scene_id}_sfx.wav) — the editable layer."""
    return Path(project.meta["reel_dir"]) / f"{scene_id}_sfx.wav"


def peaks_for_path(path: Path, buckets: int) -> list[float]:
    """Max-abs waveform envelope of an audio file, `buckets` wide."""
    import numpy as np

    if not path.is_file():
        raise NotFoundError(f"audio file missing: {path.name}")
    raw = subprocess.run(
        [FF, "-v", "error", "-i", str(path), "-f", "f32le",
         "-acodec", "pcm_f32le", "-ac", "1", "-ar", "8000", "-"],
        capture_output=True, check=True).stdout
    samples = np.frombuffer(raw, dtype=np.float32)
    if samples.size == 0:
        return [0.0] * buckets
    # pad to an even split, take per-bucket max abs
    pad = (-samples.size) % buckets
    if pad:
        samples = np.concatenate([samples, np.zeros(pad, dtype=np.float32)])
    env = np.abs(samples.reshape(-1, buckets)).max(axis=0)
    peak = float(env.max())
    return [round(float(v) / peak, 4) if peak > 0 else 0.0 for v in env]


def peaks(project, index: int, buckets: int) -> list[float]:
    """Max-abs waveform envelope of the track's source file, `buckets` wide."""
    t = track(project, index)
    return peaks_for_path(Path(t["file"]).expanduser(), buckets)


def yaml_editor():
    """A round-trip YAML loader/dumper tuned to the hand-written reel.yaml
    style: sequences indented under their key, no line rewrapping — so a
    programmatic edit reformats only the lines it touches."""
    from ruamel.yaml import YAML

    doc = YAML()
    doc.preserve_quotes = True
    doc.width = 4096
    doc.indent(mapping=2, sequence=4, offset=2)
    doc.representer.add_representer(
        type(None),
        lambda d, _: d.represent_scalar("tag:yaml.org,2002:null", "null"))
    return doc


def update_track(project, config, index: int, body: dict) -> dict:
    """Rewrite one track's timestamp note in reel.yaml, preserving comments.

    Accepts partial patches; fades are [second, volume] pairs in video time.
    """

    tracks = project.raw.get("audio")
    if not isinstance(tracks, list) or not 0 <= index < len(tracks):
        raise NotFoundError(f"no such audio track: {index}")
    if "at" not in body and "seek" not in body and "gain" not in body \
            and "fades" not in body:
        raise ValidationError(["nothing to update: expected at/seek/gain/fades"])

    fades = body.get("fades")
    if fades is not None:
        problems: list[str] = []
        if not isinstance(fades, list):
            problems.append("fades must be a list of [second, volume] pairs")
        else:
            for k in fades:
                if (not isinstance(k, list) or len(k) != 2
                        or not all(isinstance(x, (int, float)) for x in k)):
                    problems.append(f"bad keyframe {k!r}")
                    continue
                if k[1] < 0 or k[1] > 1:
                    problems.append(f"volume {k[1]} outside 0..1")
            times = [k[0] for k in fades
                     if isinstance(k, list) and len(k) == 2]
            if times != sorted(times):
                problems.append("fades must be sorted by time")
        if problems:
            raise ValidationError(problems)

    path = config.yaml_path
    doc = yaml_editor()
    with open(path) as f:
        yaml_doc = doc.load(f)
    entry = yaml_doc["audio"][index]
    if "at" in body:
        entry["at"] = round(float(body["at"]), 4)
    if "seek" in body:
        entry["seek"] = round(float(body["seek"]), 4)
    if "gain" in body:
        entry["gain"] = round(float(body["gain"]), 4)
    if fades is not None:
        entry["fades"] = [[round(float(t), 4), round(float(v), 4)]
                          for t, v in fades]
    with open(path, "w") as f:
        doc.dump(yaml_doc, f)

    # return the view derived from the file we just wrote, not the caller's
    # (possibly stale) in-memory project
    from .project import load as load_project
    return track(load_project(config), index)


def sfx_asset_path(config, slug: str) -> Path | None:
    """A named sound-effect asset from the workspace's sfx/ directory."""
    sfx_dir = Path(config.workspace) / "sfx"
    for ext in (".wav", ".mp3", ".flac", ".ogg", ".m4a"):
        p = sfx_dir / f"{slug}{ext}"
        if p.is_file():
            return p
    return None


def _sfx_scene_node(yaml_doc, scene_id: str):
    for s in yaml_doc.get("scenes") or []:
        if s.get("id") == scene_id:
            return s
    raise NotFoundError(f"unknown scene {scene_id!r}")


def sfx_events(project, scene_id: str) -> list[dict]:
    """The scene's placed sound-effect one-shots (sfx/ slug, at, gain)."""
    scene = project.scene(scene_id)
    if scene is None:
        raise NotFoundError(f"unknown scene {scene_id!r}")
    rows = (scene.get("sound_effects") or {}).get("assets") or []
    out = []
    for e in rows:
        slug = str(e.get("asset") or "")
        p = sfx_asset_path(project.config, slug)
        out.append({
            "asset": slug,
            "at": float(e.get("at", 0.0)),
            "gain": float(e.get("gain", 0.6)),
            "file": (p.name if p else None),
        })
    return out


def place_sfx_event(project, config, scene_id: str, body: dict) -> dict:
    """Add a placed one-shot to scene.sound_effects.assets in reel.yaml,
    preserving comments. body: {asset: <sfx slug>, at: <s into scene>, gain}."""
    slug = str(body.get("asset") or "").strip()
    if not slug:
        raise ValidationError(["asset is required: a slug from the sfx library"])
    if sfx_asset_path(config, slug) is None:
        raise ValidationError(
            [f"no sfx asset named {slug!r} in sfx/ — drop the file in first"])
    try:
        at = float(body.get("at", 0.0))
        gain = float(body.get("gain", 0.6))
    except (TypeError, ValueError):
        raise ValidationError(["at and gain must be numbers"])
    if not 0 <= gain <= 1:
        raise ValidationError(["gain must be 0..1"])
    if at < 0:
        raise ValidationError(["at must be >= 0 (seconds into the scene)"])

    doc = yaml_editor()
    with open(config.yaml_path) as f:
        yaml_doc = doc.load(f)
    scene = _sfx_scene_node(yaml_doc, scene_id)
    se = scene.get("sound_effects")
    if not isinstance(se, dict):
        se = {}
        scene["sound_effects"] = se
    assets = se.get("assets")
    if not isinstance(assets, list):
        assets = []
        se["assets"] = assets
    assets.append({"asset": slug, "at": at, "gain": gain})
    with open(config.yaml_path, "w") as f:
        doc.dump(yaml_doc, f)
    return {"placed": {"scene": scene_id, "asset": slug, "at": at, "gain": gain}}


def remove_sfx_event(project, config, scene_id: str, index: int) -> dict:
    """Remove one placed one-shot by index, preserving comments."""
    doc = yaml_editor()
    with open(config.yaml_path) as f:
        yaml_doc = doc.load(f)
    scene = _sfx_scene_node(yaml_doc, scene_id)
    assets = (scene.get("sound_effects") or {}).get("assets")
    if not isinstance(assets, list) or not 0 <= index < len(assets):
        raise NotFoundError(f"no such placed sfx event: {index}")
    removed = assets.pop(index)
    if not assets:  # an empty board shouldn't leave `assets: []` residue
        del scene["sound_effects"]["assets"]
    with open(config.yaml_path, "w") as f:
        doc.dump(yaml_doc, f)
    return {"removed": dict(removed)}
