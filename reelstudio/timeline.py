"""Timeline math and staleness.

Scene length is a generation-time property (frames on the H3 17n+5 grid) —
never a cut. Staleness is diff-based: a scene is stale when the generation
input the yaml would produce now differs from the one cached in the manifest
at render time (the collapse) — which subsumes config changes, shared look
edits, upstream re-renders and changed stills. A hash fallback covers
workspaces whose reel.py cannot collapse yet.
"""

import hashlib
import json

from .errors import NotFoundError
from .project import Project, file_hash

SECONDS_DIGITS = 4


def scene_frames(project: Project, scene: dict) -> int:
    return scene.get("frames", project.default_frames)


def scene_dur(project: Project, scene: dict) -> float:
    """On-screen seconds: the scene's own generated frame count at reel fps."""
    return round(scene_frames(project, scene) / project.fps, SECONDS_DIGITS)


def scene_starts(project: Project) -> list[float]:
    """Cumulative start time of each scene in the final cut."""
    out, t = [], 0.0
    for s in project.scenes:
        out.append(round(t, SECONDS_DIGITS))
        t += scene_dur(project, s)
    return out


def total_dur(project: Project) -> float:
    return round(sum(scene_dur(project, s) for s in project.scenes), SECONDS_DIGITS)


def resolve_anchor(project: Project, ref) -> dict:
    """first/last reference -> {kind, path?} for display and render."""
    if ref in (None, "", "null"):
        return {"kind": "none"}
    if ref == "prev_last":
        return {"kind": "prev_last"}
    if isinstance(ref, str) and ref.startswith("still:"):
        path = project.still_path(ref.split(":", 1)[1])
        return {"kind": "still", "path": str(path) if path else None, "ref": ref}
    return {"kind": "path", "path": str(ref)}


# -------------------------------------------------------------- hashing ----
def generation_view(project: Project, scene: dict) -> dict:
    """The generation-relevant subset of a scene, with aliases resolved and
    still anchors pinned to file content. Two scenes with equal views render
    identically (same seed randomness aside). Shared look blocks are part of
    the identity: the active style reaches every scene, a location only the
    scenes that reference it — editing them cascades staleness exactly."""
    style = project.active_style() or {}
    location = project.scene_location(scene) or {}
    view = {
        "mode": scene["video"].get("mode"),
        "first": scene["video"].get("first"),
        "last": scene["video"].get("last"),
        "description": _fmt(scene["video"].get("description"), project.aliases),
        "negative": _fmt(scene["video"].get("negative"), project.aliases),
        "frames": scene_frames(project, scene),
        "sound_effects": _fmt(scene.get("sound_effects"), project.aliases),
        "post": _fmt(scene.get("post"), project.aliases),
        "size": [project.meta.get("width"), project.meta.get("height")],
        "steps": project.meta.get("steps"),
        "style": _fmt(style, project.aliases),
        "location": _fmt(location, project.aliases),
    }
    for anchor in ("first", "last"):
        resolved = resolve_anchor(project, view[anchor])
        if resolved["kind"] == "still" and resolved.get("path"):
            # a changed still invalidates the scene that anchors on it
            view["_" + anchor + "_content"] = file_hash(resolved["path"])
    return view


def _fmt(value, aliases):
    if value is None:
        return None
    if isinstance(value, str):
        return value.format(**aliases)
    if isinstance(value, dict):
        return {k: _fmt(v, aliases) for k, v in value.items()}
    if isinstance(value, list):
        return [_fmt(v, aliases) for v in value]
    return value


def config_hash(project: Project, scene: dict) -> str:
    blob = json.dumps(generation_view(project, scene), sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def chain_hash(project: Project, scene: dict, cache: dict | None = None) -> str:
    """Config hash folded with the upstream prev_last chain, so any upstream
    re-render cascades staleness downstream without re-rendering sideways
    branches (still-anchored scenes keep their own hash)."""
    cache = cache if cache is not None else {}
    sid = scene["id"]
    if sid in cache:
        return cache[sid]
    h = config_hash(project, scene)
    if scene["video"].get("first") == "prev_last":
        prev = project.previous(sid)
        if prev is not None:
            upstream = chain_hash(project, prev, cache)
            h = hashlib.sha256(f"{h}:{upstream}".encode()).hexdigest()[:16]
    cache[sid] = h
    return h


# ------------------------------------------------------------ staleness ----
def stale_scenes(project: Project, manifest: dict, reel_dir: str = "",
                 collapse: dict | None = None) -> list[str]:
    """Scene ids whose recorded generation input no longer matches what the
    yaml would generate now.

    Primary mechanism: `collapse` (reel.py's merged generation input per
    scene) diffed against the artifact cached in the manifest at render time.
    It subsumes junction identity — a resolved prev_last anchor carries the
    upstream file's content hash, so an upstream re-render cascades here
    automatically. When the workspace cannot collapse (older reel.py), fall
    back to the hash chain."""
    from pathlib import Path

    if collapse is not None:
        stale = []
        for s in project.scenes:
            sid = s["id"]
            entry = manifest.get("scenes", {}).get(sid)
            if entry is None:
                stale.append(sid)
                continue
            if entry.get("generation") != collapse.get(sid):
                stale.append(sid)
                continue
            video_file = (entry.get("video") or {}).get("path", {}).get("file")
            if not video_file or not (Path(reel_dir) / video_file).exists():
                stale.append(sid)
        return stale

    cache = {}
    stale = []
    for s in project.scenes:
        entry = manifest.get("scenes", {}).get(s["id"])
        if entry is None:
            stale.append(s["id"])
            continue
        if entry.get("chain_hash") != chain_hash(project, s, cache):
            stale.append(s["id"])
            continue
        video_file = (entry.get("video") or {}).get("path", {}).get("file")
        if not video_file or not (Path(reel_dir) / video_file).exists():
            stale.append(s["id"])
            continue
        # junction identity: an upstream re-render (even same-config, new seed)
        # invalidates a prev_last-dependent scene — the anchored frame moved
        up = entry.get("upstream")
        if up:
            prev_entry = manifest.get("scenes", {}).get(up["scene_id"], {})
            current = (prev_entry.get("video") or {}).get("path", {}).get("file")
            if current != up.get("file"):
                stale.append(s["id"])
    return stale


def stale_music(project: Project, manifest: dict) -> list[str]:
    """Music segment names whose caption/gain/timespan changed."""
    from .audio import music_segments  # local import: audio owns segments

    out = []
    current = {m["name"]: m for m in music_segments(project)}
    recorded = manifest.get("music", {})
    for name, m in current.items():
        entry = recorded.get(name)
        if entry is None or entry.get("hash") != m["hash"]:
            out.append(name)
    return [n for n in recorded if n not in current] + out


def scene_view(project: Project, scene_id: str) -> dict:
    """The per-scene state the UI renders. Raises NotFoundError on bad ids."""
    scene = project.scene(scene_id)
    if scene is None:
        raise NotFoundError(f"unknown scene {scene_id!r}")
    return {
        "id": scene["id"],
        "next": scene.get("next"),
        "index": [s["id"] for s in project.scenes].index(scene_id),
        "mode": scene["video"].get("mode"),
        "frames": scene_frames(project, scene),
        "duration_s": scene_dur(project, scene),
        "first": resolve_anchor(project, scene["video"].get("first")),
        "last": resolve_anchor(project, scene["video"].get("last")),
        "description": scene["video"].get("description", ""),
        "location": scene.get("location"),
        "has_freeze": bool(scene.get("post", {}).get("freeze")),
        "has_bell": bool(scene.get("sound_effects", {}).get("bell")),
        "bell_at": (scene.get("sound_effects", {}).get("bell_at")
                    if scene.get("sound_effects", {}).get("bell") else None),
        "has_sfx": bool(scene.get("sound_effects", {}).get("soundscape")),
    }
