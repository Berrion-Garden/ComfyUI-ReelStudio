"""Asset library: images, character pools, themes, audio — slugs and labels.

Derivation, not duplication: labels come from the reel itself (the stills map,
which scenes use which anchor), from directory convention
(`characters/<slug>/`, `images/`, `audio/`, `themes/`), and from the optional
`assets.yaml`, which can attach extra labels to any relative path — that is how
an image cross-groups. There is no second hand-maintained index: the API
response is the index, computed over a cheap directory walk.
"""

from dataclasses import dataclass, field, asdict
from pathlib import Path

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
AUDIO_EXTS = {".mp3", ".wav", ".flac", ".m4a", ".ogg"}


@dataclass
class Asset:
    path: str            # absolute
    slug: str            # filename stem
    group: str           # characters | scenes | custom | themes | audio
    labels: list[str] = field(default_factory=list)
    used_by: list[str] = field(default_factory=list)  # scene ids (images)


def _labels_file(workspace: Path) -> dict[str, list[str]]:
    """Declared extra labels from assets.yaml: `labels: {<rel path>: [..]}`."""
    import yaml

    f = Path(workspace) / "assets.yaml"
    if not f.exists():
        return {}
    raw = yaml.safe_load(f.read_text()) or {}
    return {str(k): [str(x) for x in v] for k, v in (raw.get("labels") or {}).items()}


def _rel(path: Path, roots: list[Path]) -> str:
    """A stable key for assets.yaml labels: first root-relative match."""
    for r in roots:
        try:
            return str(path.relative_to(r))
        except ValueError:
            continue
    return path.name


def index_assets(workspace: str | Path, project) -> dict:
    ws = Path(workspace)
    still_dir = Path(project.meta["still_dir"])
    roots = [ws, still_dir]
    declared = _labels_file(ws)

    def mk(path: Path, group: str, labels: list[str], used_by: list[str] | None = None) -> dict:
        rel = _rel(path, roots)
        merged = list(dict.fromkeys(labels + declared.get(rel, [])))
        # the reel's naming convention appends frame counters ("name_00001_");
        # the slug is the human part
        return {"path": str(path), "slug": path.stem.rstrip("_") or path.stem,
                "group": group, "labels": merged, "used_by": used_by or []}

    groups: dict[str, list[dict]] = {"characters": [], "scenes": [],
                                     "custom": [], "themes": [], "audio": [],
                                     "sfx": []}

    # scenes — the stills the timeline actually anchors on
    def _still_refs(scene: dict) -> list[str]:
        refs = []
        for key in ("first", "last"):
            a = scene.get("video", {}).get(key)
            if isinstance(a, dict) and a.get("kind") == "still":
                refs.append(a.get("ref"))
            elif isinstance(a, str) and a.startswith("still:"):
                refs.append(a[len("still:"):])
        return [r for r in refs if r]

    for name, _ in project.stills.items():
        p = project.still_path(name)
        if p is None or not p.exists():
            continue
        users = [s["id"] for s in project.scenes if name in _still_refs(s)]
        groups["scenes"].append(mk(
            p, "scenes", ["still", f"still:{name}"], users))

    # characters — pools of poses under characters/<slug>/
    for pool in sorted((ws / "characters").glob("*") if (ws / "characters").exists() else []):
        if not pool.is_dir():
            continue
        for p in sorted(pool.iterdir()):
            if p.suffix.lower() in IMAGE_EXTS:
                pose = p.stem.rstrip("_") or p.stem
                groups["characters"].append(mk(
                    p, "characters", [f"char:{pool.name}", f"pose:{pose}"]))

    # custom — anything the operator drops into images/
    custom_root = ws / "images"
    if custom_root.exists():
        for p in sorted(custom_root.rglob("*")):
            if p.is_file() and p.suffix.lower() in IMAGE_EXTS:
                groups["custom"].append(mk(p, "custom", ["custom"]))

    # themes — LORA/style descriptors as yaml: {slug, lora, trigger, labels}
    themes_root = ws / "themes"
    if themes_root.exists():
        import yaml

        for p in sorted(themes_root.glob("*.yaml")):
            raw = yaml.safe_load(p.read_text()) or {}
            slug = raw.get("slug", p.stem)
            labels = [f"theme:{slug}"] + [str(x) for x in raw.get("labels", [])]
            groups["themes"].append(mk(p, "themes", labels))

    # audio — rendered music segments, then any files under audio/
    reel_dir = Path(project.meta["reel_dir"])
    for p in sorted(reel_dir.glob("music_*")):
        if p.suffix.lower() in AUDIO_EXTS:
            name = p.name.split("_")[1]
            groups["audio"].append(mk(p, "audio", ["music", f"track:{name}"]))
    audio_root = ws / "audio"
    if audio_root.exists():
        for p in sorted(audio_root.rglob("*")):
            if p.is_file() and p.suffix.lower() in AUDIO_EXTS:
                groups["audio"].append(mk(p, "audio", ["audio"]))

    # sfx — named sound effects the yaml references (`bell: school_bell`);
    # the seedbed of the sound-effect board
    sfx_root = ws / "sfx"
    if sfx_root.exists():
        for p in sorted(sfx_root.rglob("*")):
            if p.is_file() and p.suffix.lower() in AUDIO_EXTS:
                groups["sfx"].append(mk(p, "sfx", ["sfx", f"sfx:{p.stem}"]))

    return {"groups": groups}


def asset_file(path: str, allowed_roots: list[str | Path]) -> Path:
    """Resolve a request path against the allow-list of roots (no escaping)."""
    from .errors import ForbiddenError

    p = Path(path).resolve()
    for root in allowed_roots:
        r = Path(root).resolve()
        if r == p or r in p.parents:
            return p
    raise ForbiddenError(f"path outside the asset roots: {path}")
