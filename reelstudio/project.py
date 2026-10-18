"""Project model: load, validate and save reel.yaml.

reel.yaml is the single source of truth (inherited from the anime_reel
pipeline): one scene = one narrative chunk with video / sound_effects / music
layers, chained by `next:` slugs. This module owns the structure rules; the
timeline module owns the time math.
"""

import os
from pathlib import Path

import yaml

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
        """Resolve a `stills:` entry to its file in meta.still_dir."""
        rel = self.stills.get(name)
        if rel is None:
            return None
        return Path(self.meta["still_dir"]) / (rel + "_.png")

    # -------------------------------------------------------------- io -----
    def warnings(self) -> list[str]:
        return validate(self)

    def to_yaml_text(self) -> str:
        return yaml.safe_dump(self.raw, sort_keys=False, allow_unicode=True)

    def save(self, text: str | None = None) -> list[str]:
        """Atomic save; raises ValidationError on structural errors. Returns
        the non-blocking warnings (e.g. off-grid frames)."""
        if text is not None:
            self.raw = yaml.safe_load(text)
        warnings = validate(self)
        tmp = self.config.yaml_path.with_suffix(".yaml.tmp")
        tmp.write_text(text if text is not None else self.to_yaml_text())
        os.replace(tmp, self.config.yaml_path)
        return warnings


def load(config: Config) -> Project:
    raw = yaml.safe_load(config.yaml_path.read_text())
    project = Project(raw, config)
    validate(project)
    return project


# ---------------------------------------------------------------- rules ----
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
                if ref.split(":", 1)[1] not in project.stills:
                    problems.append(f"{sid}: unknown still ref {ref!r}")

        music = s.get("music")
        if isinstance(music, dict) and not (music.get("name") and music.get("caption")):
            problems.append(f"{sid}: music segments need name and caption")

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
