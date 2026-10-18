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


def peaks(project, index: int, buckets: int) -> list[float]:
    """Max-abs waveform envelope of the track's source file, `buckets` wide."""
    import numpy as np

    t = track(project, index)
    path = Path(t["file"]).expanduser()
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


def update_track(project, config, index: int, body: dict) -> dict:
    """Rewrite one track's timestamp note in reel.yaml, preserving comments.

    Accepts partial patches; fades are [second, volume] pairs in video time.
    """
    from ruamel.yaml import YAML

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
    doc = YAML()
    doc.preserve_quotes = True
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
