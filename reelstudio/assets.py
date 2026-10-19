"""Asset library: images, character pools, themes, audio — slugs and labels.

Derivation, not duplication: labels come from the reel itself (the scene
anchors, which scenes use which still), from directory convention
(`characters/<slug>/`, `images/`, `audio/`, `themes/`), and from the optional
`assets.yaml`, which can attach extra labels to any relative path — that is how
an image cross-groups and how a `still:<name>` pick is recorded. There is no
second hand-maintained index: the API response is the index, computed over a
cheap directory walk.
"""

import os
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


def _label_file(ws: Path, still_dir: Path, rel: str) -> Path:
    """The inverse of _rel for an assets.yaml key: the file it declares
    (workspace first, the still_dir serving its bare stem convention)."""
    p = ws / rel
    return p if p.is_file() else still_dir / rel


def labeled_stills(workspace: str | Path, still_dir: str | Path) -> dict[str, list[Path]]:
    """The `still:<name>` picks declared in assets.yaml: name -> tagged
    file(s). The label is the single owner of "which option was picked"
    among the generated candidates (project.still_path branch b)."""
    ws, sd = Path(workspace), Path(still_dir)
    out: dict[str, list[Path]] = {}
    for rel, labels in _labels_file(ws).items():
        for label in labels:
            if label.startswith("still:"):
                out.setdefault(label.split(":", 1)[1], []).append(
                    _label_file(ws, sd, rel))
    return out


def pool_files(workspace: str | Path) -> list[Path]:
    """Every image in the standardized pools — `characters/<char>/**`,
    `backgrounds/<loc>/**`, `images/**`. The directory is the grouping
    owner; the slug scan (project.still_path branch c) walks them."""
    ws = Path(workspace)
    files: list[Path] = []
    for pool in ("characters", "backgrounds", "images"):
        root = ws / pool
        if root.is_dir():
            files += [p for p in root.rglob("*")
                      if p.is_file() and p.suffix.lower() in IMAGE_EXTS]
    return sorted(files)


def pool_matches(workspace: str | Path, slug: str) -> list[Path]:
    """Pool files whose name carries the slug — exact stem first, then
    partial (the reel's naming convention appends frame counters)."""
    files = pool_files(workspace)
    exact = [p for p in files if p.stem == slug]
    return exact + [p for p in files if p.stem != slug and slug in p.stem]


def pick_still(workspace: str | Path, still_dir: str | Path, path: str,
               name: str) -> dict:
    """The pick flow's label half: `still:<name>` moves to the chosen file
    — off every other file it tags (a name can anchor exactly one pick) —
    keeping the chosen file's other labels. set_labels is the writer:
    assets.yaml stays the single owner of declared labels."""
    ws, sd = Path(workspace), Path(still_dir)
    p = asset_file(path, [ws, sd])
    tag = f"still:{name}"
    rel = _rel(p, [ws, sd])
    declared = _labels_file(ws)
    released: list[str] = []
    for r, labels in declared.items():
        if tag in labels and r != rel:
            set_labels(ws, sd, str(_label_file(ws, sd, r)),
                       [x for x in labels if x != tag])
            released.append(r)
    current = declared.get(rel) or []
    if tag not in current:
        current = [*current, tag]
        set_labels(ws, sd, str(p), current)
    return {"picked": rel, "released": released, "labels": current}


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
                                     "stills": [], "custom": [],
                                     "backgrounds": [], "themes": [],
                                     "audio": [], "sfx": []}

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

    for name in project.still_names():
        p = project.still_path(name)
        if p is None or not p.exists():
            continue
        users = [s["id"] for s in project.scenes if name in _still_refs(s)]
        groups["scenes"].append(mk(
            p, "scenes", ["still", f"still:{name}"], users))

    # stills — every other image in still_dir: generation candidates the
    # operator picks from (the pick then anchors by `still:<name>` label)
    anchored = {p.resolve() for p in
                (project.still_path(n) for n in project.still_names()) if p}
    for p in sorted(still_dir.glob("*.png") if still_dir.exists() else []):
        if p.is_file() and p.resolve() not in anchored:
            groups["stills"].append(mk(p, "stills", ["candidate"]))

    # characters — two pools per character: references/ (the operator's
    # uploaded base images — the source `attributes` are pulled from) and
    # posed_stills/ (generated reference stills). Legacy flat files keep
    # working; the _refNN/_sheetNN filename convention marks them posed.
    # Everything in characters/<char>/** belongs to that char — the pool
    # directory is the grouping owner, no label required.
    for pool in sorted((ws / "characters").glob("*") if (ws / "characters").exists() else []):
        if not pool.is_dir():
            continue
        for p in sorted(pool.rglob("*")):
            if not p.is_file() or p.suffix.lower() not in IMAGE_EXTS:
                continue
            parts = p.relative_to(pool).parts
            if "references" in parts:
                kind = "reference"
            elif "posed_stills" in parts:
                kind = "posed"
            else:  # legacy flat file at the pool root
                kind = ("posed" if ("_posed_" in p.stem or "_ref" in p.stem
                                    or "_sheet_" in p.stem) else "reference")
            pose = p.stem.rstrip("_") or p.stem
            groups["characters"].append(mk(
                p, "characters", [f"char:{pool.name}", f"pose:{pose}", kind]))

    # custom — anything the operator drops into images/
    custom_root = ws / "images"
    if custom_root.exists():
        for p in sorted(custom_root.rglob("*")):
            if p.is_file() and p.suffix.lower() in IMAGE_EXTS:
                groups["custom"].append(mk(p, "custom", ["custom"]))

    # backgrounds — location pools under backgrounds/<location>/ (the plate
    # a shot references), labeled like character pools. Everything in
    # backgrounds/<loc>/** belongs to that location — directory-derived.
    bg_root = ws / "backgrounds"
    if bg_root.exists():
        for loc in sorted(bg_root.iterdir()):
            if not loc.is_dir():
                continue
            for p in sorted(loc.rglob("*")):
                if p.is_file() and p.suffix.lower() in IMAGE_EXTS:
                    groups["backgrounds"].append(mk(
                        p, "backgrounds", [f"loc:{loc.name}", "background"]))

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


def set_labels(workspace: str | Path, still_dir: str | Path, path: str,
               labels: list[str]) -> dict:
    """Rewrite one asset's declared labels in assets.yaml — the single owner
    of declared labels — comment- and format-preserving. Labels are typed
    free-form: `char:<slug>`, `scene:<slug>` (foreign key to the scene id),
    `cond:<x>`, or any other tag. An empty list removes the entry."""
    from ruamel.yaml import YAML

    roots = [Path(workspace), Path(still_dir)]
    p = asset_file(path, roots)
    rel = _rel(p, roots)

    f = Path(workspace) / "assets.yaml"
    doc = YAML()
    doc.preserve_quotes = True
    doc.width = 4096
    declared = {}
    if f.exists():
        declared = doc.load(f) or {}
    labels_map = declared.setdefault("labels", {})
    if labels:
        labels_map[rel] = [str(x) for x in labels]
    else:
        labels_map.pop(rel, None)
    # atomic replace: a concurrent reader (the asset index on every UI poll)
    # must never see a half-written yaml — a partial parse there storms
    # exceptions into the server loop and wedges it
    tmp = f.with_suffix(f.suffix + ".tmp")
    with open(tmp, "w") as fh:
        doc.dump(declared, fh)
    os.replace(tmp, f)
    return {"asset": rel, "labels": labels_map.get(rel, [])}
