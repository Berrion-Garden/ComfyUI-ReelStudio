"""Project model: load, validate and save reel.yaml.

reel.yaml is the single source of truth (inherited from the anime_reel
pipeline): one scene = one narrative chunk with video / sound_effects / music
layers, chained by `next:` slugs. Shared look machinery — `styles:` (the
active one is injected into every prompt) and `locations:` (injected into the
scenes that reference them) — lives here too. This module owns the structure
rules; the timeline module owns the time math.
"""

import os
from pathlib import Path

import yaml

from . import assets as assets_mod
from .config import Config
from .errors import ValidationError

H3_FRAME_GRID = 17  # valid clip lengths are 17n + 5

VALID_VIDEO_MODES = ("i2v", "t2v", "fl2v")


def file_hash(path: str | os.PathLike) -> str:
    import hashlib

    p = Path(path)
    if not p.exists():
        return "missing"
    return hashlib.sha256(p.read_bytes()).hexdigest()[:16]


class Project:
    """A loaded reel.yaml. Raw dicts stay raw — the agent and UI edit the
    YAML, we only validate and interpret it."""

    def __init__(self, raw: dict, config: Config):
        self.raw = raw
        self.config = config

    # ------------------------------------------------------------ access ---
    @property
    def meta(self) -> dict:
        return self.raw.get("meta", {})

    @property
    def aliases(self) -> dict:
        return self.raw.get("aliases", {})

    @property
    def stills(self) -> dict:
        return self.raw.get("stills", {})

    @property
    def styles(self) -> dict:
        return self.raw.get("styles", {})

    @property
    def active_style_name(self) -> str | None:
        return self.raw.get("style")

    def active_style(self) -> dict | None:
        """The {pro, con} block injected into every video prompt."""
        name = self.active_style_name
        return self.styles.get(name) if name else None

    @property
    def locations(self) -> dict:
        return self.raw.get("locations", {})

    def scene_location(self, scene: dict) -> dict | None:
        """The {pro, con} block for the scene's `location:` slug, if any."""
        return self.locations.get(scene.get("location")) \
            if scene.get("location") else None

    @property
    def scenes(self) -> list[dict]:
        return self.raw.get("scenes", [])

    def scene(self, scene_id: str) -> dict | None:
        return self.by_id().get(scene_id)

    def by_id(self) -> dict[str, dict]:
        return {s["id"]: s for s in self.scenes}

    def previous(self, scene_id: str) -> dict | None:
        ids = [s["id"] for s in self.scenes]
        if scene_id in ids and ids.index(scene_id) > 0:
            return self.scenes[ids.index(scene_id) - 1]
        return None

    @property
    def fps(self) -> float:
        return self.meta.get("fps", 24)

    @property
    def default_frames(self) -> int:
        return self.meta.get("frames", 107)

    def still_path(self, name: str) -> Path | None:
        """Resolve a `still:<name>` anchor to its file. Order: (a) the legacy
        `stills:` entry (existing behavior), (b) the `still:<name>` label
        pick in assets.yaml, (c) a unique slug match in the standardized
        pools. None when ambiguous or unknown — validation names the
        candidates."""
        p, _ = self._still_resolution(name)
        return p

    def still_candidates(self, name: str) -> list[Path]:
        """The files among which the pick must be labeled — empty when the
        name resolves to nothing at all."""
        return self._still_resolution(name)[1]

    def _still_resolution(self, name: str) -> tuple[Path | None, list[Path]]:
        """The shared tail of still_path / still_candidates: {path, candidates}."""
        ws, still_dir = self.config.workspace, Path(self.meta.get("still_dir", ""))
        rel = self.stills.get(name)
        if rel is not None:
            value = str(rel)
            for cand in _legacy_still_candidates(ws, still_dir, value):
                if cand.is_file():
                    return cand, []
            # the entry is stale — the app figures it out below: the pick
            # label, then the pool scan; slugs are the anchor name and the
            # entry's own basename (heals paths written from another root)
            slugs = [name, Path(value).stem]
        else:
            slugs = [name]

        picks = assets_mod.labeled_stills(ws, still_dir).get(name) or []
        if len(picks) == 1:
            return picks[0], []
        if picks:
            return None, picks  # the pick itself is ambiguous

        matches: list[Path] = []
        for slug in slugs:
            for p in assets_mod.pool_matches(ws, slug):
                if p not in matches:
                    matches.append(p)
        if len(matches) == 1:
            return matches[0], []
        if matches:
            return None, matches

        if rel is not None:
            # a named legacy entry is never "unknown": its conventional
            # path (missing on disk) is the read model's present:false signal
            return Path(still_dir) / (value + "_.png"), []
        return None, []

    def still_names(self) -> list[str]:
        """Every `still:<name>` in play: the legacy stills: map plus the refs
        the scenes actually anchor on (a label pick needs no map entry)."""
        names = list(self.stills)
        for s in self.scenes:
            for key in ("first", "last"):
                a = s.get("video", {}).get(key)
                ref = a.get("ref") if isinstance(a, dict) else a
                if isinstance(ref, str) and ref.startswith("still:"):
                    name = ref.split(":", 1)[1]
                    if name not in names:
                        names.append(name)
        return names

    # -------------------------------------------------------------- io -----
    def warnings(self) -> list[str]:
        return validate(self)

    def to_yaml_text(self) -> str:
        return yaml.safe_dump(self.raw, sort_keys=False, allow_unicode=True)

    def save(self, text: str | None = None) -> list[str]:
        """Atomic save; raises ValidationError on structural errors (parse
        errors included — a malformed file must never reach disk). Returns
        the non-blocking warnings (e.g. off-grid frames)."""
        if text is not None:
            self.raw = _safe_load(text)
        warnings = validate(self)
        tmp = self.config.yaml_path.with_suffix(".yaml.tmp")
        tmp.write_text(text if text is not None else self.to_yaml_text())
        os.replace(tmp, self.config.yaml_path)
        return warnings


def _safe_load(text: str) -> dict:
    import yaml as _yaml

    try:
        data = _yaml.safe_load(text)
    except _yaml.YAMLError as e:
        raise ValidationError([f"malformed yaml: {e}"]) from e
    if not isinstance(data, dict):
        raise ValidationError(["reel.yaml must be a yaml mapping at the top level"])
    return data


def _legacy_still_candidates(ws: Path, still_dir: Path, value: str) -> list[Path]:
    """Every file a legacy `stills:` value may name: an absolute path, or
    relative to the workspace or the still_dir — the still_dir stem
    convention completing `name_` (same order reel.py resolves anchors in)."""
    out = [Path(value)]
    for base in (ws, still_dir):
        out += [base / value, base / (value + "_.png")]
    return list(dict.fromkeys(out))


def load(config: Config) -> Project:
    raw = _safe_load(config.yaml_path.read_text())
    project = Project(raw, config)
    validate(project)
    return project


def anchor_still(config: Config, scene_id: str,
                 anchor: str, name: str) -> dict:
    """The pick flow's yaml half: point the scene's `video.<anchor>` at
    `still:<name>` and drop the legacy `stills:` path entry for that name
    (other entries stay) — reel.yaml never grows absolute paths again.
    Comment-preserving (the reels are heavily annotated); the mutated tree
    is validated before it reaches disk."""
    from ruamel.yaml import YAML

    ry = YAML()
    ry.preserve_quotes = True
    ry.width = 4096
    doc = ry.load(config.yaml_path) or {}
    scene = next((s for s in (doc.get("scenes") or [])
                  if s.get("id") == scene_id), None)
    if scene is None:
        raise ValidationError([f"unknown scene {scene_id!r}"])
    scene.setdefault("video", {})[anchor] = f"still:{name}"
    stills = doc.get("stills") or {}
    removed = None
    if name in stills:
        removed = stills.pop(name)
    validate(Project(doc, config))
    with open(config.yaml_path, "w") as fh:
        ry.dump(doc, fh)
    return {"scene": scene_id, "anchor": anchor,
            "ref": f"still:{name}", "removed_stills_entry": removed is not None}


# ---------------------------------------------------------------- rules ----
def _validate_look_block(project: Project, kind: str, blocks: dict,
                         problems: list[str]) -> None:
    """Shared shape for `styles:`/`locations:` entries: a map of slug ->
    {pro (required), con (optional)}. Alias refs must resolve everywhere —
    a typo in a shared block would otherwise poison every prompt."""
    if not isinstance(blocks, dict):
        problems.append(f"{kind}: must be a map of slug -> "
                        "{pro: ..., con: ...} blocks")
        return
    for slug, block in blocks.items():
        where = f"{kind}.{slug}"
        if not isinstance(block, dict):
            problems.append(f"{where}: needs pro (and optional con) strings")
            continue
        pro = block.get("pro")
        if not pro or not isinstance(pro, str):
            problems.append(f"{where}: pro is required and must be a string")
        for part in ("pro", "con"):
            text = block.get(part)
            if text is not None and not isinstance(text, str):
                problems.append(f"{where}.{part}: must be a string")
            if isinstance(text, str) and text:
                try:
                    text.format(**project.aliases)
                except (KeyError, IndexError) as e:
                    problems.append(f"{where}.{part}: unknown alias ref {e} "
                                    f"(known aliases: {list(project.aliases)})")


def validate(project: Project) -> list[str]:
    """Raises ValidationError on structural errors; returns warnings (e.g.
    off-grid frame counts) that do not block work."""
    problems: list[str] = []
    warnings: list[str] = []
    scenes = project.scenes
    meta = project.meta

    if not scenes:
        problems.append("no scenes defined")
    for required in ("fps", "frames", "width", "height", "still_dir", "reel_dir"):
        if required not in meta:
            problems.append(f"meta.{required} is required")

    _validate_look_block(project, "styles", project.styles, problems)
    if project.styles:
        name = project.active_style_name
        if not name:
            problems.append(f"style: pick the active style "
                            f"(known: {list(project.styles)})")
        elif name not in project.styles:
            problems.append(f"style: {name!r} is not defined in styles "
                            f"(known: {list(project.styles)})")
    elif project.active_style_name:
        problems.append("style: selector without a styles map")
    _validate_look_block(project, "locations", project.locations, problems)

    ids = [s.get("id") for s in scenes]
    if len(set(ids)) != len(ids):
        dupes = {i for i in ids if ids.count(i) > 1}
        problems.append(f"duplicate scene ids: {sorted(dupes)}")

    for i, s in enumerate(scenes):
        sid = s.get("id", f"<scene {i}>")
        video = s.get("video", {})
        if video.get("mode") not in VALID_VIDEO_MODES:
            problems.append(f"{sid}: video.mode must be one of {VALID_VIDEO_MODES}")
        if not video.get("description"):
            problems.append(f"{sid}: video.description is required")

        frames = s.get("frames", meta.get("frames"))
        if frames is None:
            problems.append(f"{sid}: no frames and no meta.frames default")
        elif not (isinstance(frames, int) and frames > 0):
            problems.append(f"{sid}: frames must be a positive integer, got {frames!r}")
        elif (frames - 5) % H3_FRAME_GRID != 0:
            warnings.append(
                f"{sid}: {frames} frames is off the H3 17n+5 grid "
                f"(nearest: {17 * round((frames - 5) / 17) + 5})")

        for anchor in ("first", "last"):
            ref = video.get(anchor)
            if ref is None or ref in ("", "null"):
                continue
            if ref == "prev_last":
                if i == 0:
                    problems.append(f"{sid}: first scene cannot anchor on prev_last")
                continue
            if isinstance(ref, str) and ref.startswith("still:"):
                name = ref.split(":", 1)[1]
                if project.still_path(name) is None:
                    cands = project.still_candidates(name)
                    if cands:
                        warnings.append(
                            f"{sid}: {ref!r} is ambiguous — no still:<name> "
                            f"label pick, candidates: "
                            f"{', '.join(sorted(c.name for c in cands))}")
                    else:
                        problems.append(f"{sid}: unknown still ref {ref!r}")

        music = s.get("music")
        if isinstance(music, dict) and not (music.get("name") and music.get("caption")):
            problems.append(f"{sid}: music segments need name and caption")

        loc = s.get("location")
        if loc is not None and loc not in project.locations:
            problems.append(f"{sid}: unknown location {loc!r} "
                            f"(known: {list(project.locations)})")

        post = s.get("post", {}).get("freeze")
        if post and "at_s" not in post:
            problems.append(f"{sid}: post.freeze needs at_s")

    # chain agreement: list order == next order
    for i, s in enumerate(scenes[:-1]):
        expected = ids[i + 1] if i + 1 < len(scenes) else None
        if s.get("next") != expected:
            problems.append(f"chain break at {s.get('id')}: next={s.get('next')!r}, expected {expected!r}")
    if scenes and scenes[-1].get("next") is not None:
        problems.append(f"last scene {ids[-1]!r} must end the chain (next: null)")

    music_names = [s["music"]["name"] for s in scenes if isinstance(s.get("music"), dict)]
    if len(set(music_names)) != len(music_names):
        problems.append("music segment names must be unique")

    if problems:
        raise ValidationError(problems)
    return warnings
