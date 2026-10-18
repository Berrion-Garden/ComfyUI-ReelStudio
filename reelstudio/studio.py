"""The studio wrapper — one YAML layer above reel.yaml.

A studio is a directory holding `studio.yaml` (the registry of scenes) and
one shared `reel.py` (the pipeline — never duplicated). Each scene is a
self-contained directory under `scenes/` (reel.yaml, assets.yaml, and the
asset libraries). `resolve()` accepts the root OR any scene dir as the
configured workspace; an unmigrated workspace is an implicit one-scene
studio that `save_as()` turns into the real nested structure.
"""

from dataclasses import dataclass
from pathlib import Path

import yaml

from .errors import NotFoundError, ValidationError

STUDIO_YAML = "studio.yaml"
SCENES_DIR = "scenes"

# What belongs to a scene and moves with it during save_as(); reel.py and
# studio.yaml stay at the root on purpose.
SCENE_FILES = ("reel.yaml", "assets.yaml", "characters", "backgrounds",
               "sfx", "audio", "images", "themes", "README.md", ".work")


@dataclass(frozen=True)
class Scene:
    slug: str
    title: str
    dir: str  # studio-root-relative, posix


@dataclass(frozen=True)
class Studio:
    root: Path
    title: str
    saved: bool  # False = implicit single-scene workspace, no studio.yaml yet
    scenes: tuple[Scene, ...]
    current: str

    def view(self, scene_extra=None) -> dict:
        return {
            "title": self.title,
            "current": self.current,
            "saved": self.saved,
            "scenes": [{
                "slug": s.slug, "title": s.title, "dir": s.dir,
                "current": s.slug == self.current,
                **(scene_extra(s) if scene_extra else {}),
            } for s in self.scenes],
        }

    def scene(self, slug: str) -> Scene:
        for s in self.scenes:
            if s.slug == slug:
                return s
        raise NotFoundError(f"unknown scene {slug!r} "
                            f"(known: {[s.slug for s in self.scenes]})")

    def dir_of(self, slug: str) -> Path:
        s = self.scene(slug)
        p = (self.root / s.dir).resolve()
        if not p.is_relative_to(self.root.resolve()):
            raise ValidationError([f"scene {slug!r} escapes the studio root"])
        return p

    @property
    def scene_dir(self) -> Path:
        return self.dir_of(self.current)


def _parse(root: Path, doc, saved: bool) -> Studio:
    if not isinstance(doc, dict) or not isinstance(doc.get("scenes"), dict) \
            or not doc["scenes"]:
        raise ValidationError([f"{STUDIO_YAML} must map slugs under 'scenes'"])
    current = doc.get("current")
    scenes = tuple(
        Scene(str(slug), str((v or {}).get("title") or slug),
              str((v or {}).get("dir") or f"{SCENES_DIR}/{slug}"))
        for slug, v in doc["scenes"].items())
    known = [s.slug for s in scenes]
    if current not in known:
        raise ValidationError([f"{STUDIO_YAML}: current {current!r} "
                               f"not in scenes {known}"])
    return Studio(root=root, title=str(doc.get("title") or root.name),
                  saved=saved, scenes=scenes, current=str(current))


def resolve(workspace: str | Path) -> Studio:
    """The studio for a configured workspace: the workspace itself (root)
    or any ancestor holding studio.yaml (a scene dir). Without studio.yaml,
    the workspace is an implicit one-scene studio."""
    ws = Path(workspace).expanduser().resolve()
    for root in (ws, *ws.parents):
        if (root / STUDIO_YAML).is_file():
            doc = yaml.safe_load((root / STUDIO_YAML).read_text())
            return _parse(root, doc, saved=True)
    return Studio(root=ws, title=ws.name, saved=False,
                  scenes=(Scene(ws.name, ws.name, "."),), current=ws.name)


def _write(studio: Studio) -> None:
    doc = {
        "title": studio.title,
        "current": studio.current,
        "scenes": {s.slug: {"title": s.title, "dir": s.dir}
                   for s in studio.scenes},
    }
    (studio.root / STUDIO_YAML).write_text(yaml.safe_dump(doc, sort_keys=False))


def save_as(workspace: str | Path, slug: str, title: str | None) -> Path:
    """Persist the workspace as a named scene. On an implicit studio this
    performs the migration — the project moves into scenes/<slug>/ and the
    wrapper is written — and returns the new scene dir. On a saved studio it
    just persists current/title and returns that scene's dir."""
    studio = resolve(workspace)
    slug = str(slug).strip()
    if not slug or not slug.replace("-", "").replace("_", "").isalnum():
        raise ValidationError(["slug must be alphanumeric (-, _)"])
    if studio.saved:
        # the configured workspace may be a scene dir whose registry lives
        # at an ancestor — update THAT registry, never re-migrate in place
        studio.scene(slug)
        updated = Scene(slug, title or studio.scene(slug).title,
                        studio.scene(slug).dir)
        _write(Studio(studio.root, title or studio.title, True,
                      tuple(updated if s.slug == slug else s
                            for s in studio.scenes), slug))
        return studio.dir_of(slug)

    root = studio.root
    scene = root / SCENES_DIR / slug
    if scene.exists():
        raise ValidationError([f"{scene} already exists"])
    scene.mkdir(parents=True)
    for name in SCENE_FILES:
        if (root / name).exists():
            (root / name).rename(scene / name)
    _write(Studio(root, title or slug, True,
                  (Scene(slug, title or slug, f"{SCENES_DIR}/{slug}"),), slug))
    return scene


def open_scene(workspace: str | Path, slug: str) -> Path:
    """Switch the current scene; returns its directory to rebind to."""
    studio = resolve(workspace)
    if not studio.saved:
        raise NotFoundError("this workspace has no scene registry yet — "
                            "save it as a scene first")
    studio.scene(slug)
    _write(Studio(studio.root, studio.title, True, studio.scenes, slug))
    return studio.dir_of(slug)


SCAFFOLD = """\
# {title} — one scene = one narrative chunk (video / sound_effects / music).
meta:
  comfy: {comfy}
  fps: {fps}
  frames: {frames}
  width: {width}
  height: {height}
  steps: {steps}
  still_dir: {still_dir}
  reel_dir: {reel_dir}
  final: {final}
  work: {work}

aliases: {{}}
styles:
  anime:
    pro: 2D anime, cel-shaded, clean bold line art, vibrant flat colors
    con: photorealistic, 3D rendering, live action, text, watermark
style: anime
locations: {{}}
stills: {{}}

scenes:
  - id: s1_open
    next: null
    video:
      mode: i2v
      first: null
      last: null
      description: |
        An establishing shot.
"""


def create_scene(workspace: str | Path, slug: str, title: str | None,
                 seed_meta: dict) -> Path:
    """Scaffold a fresh, valid scene directory and make it current.
    seed_meta is the current scene's reel.yaml meta — the template for the
    render defaults and the parent dir of the new scene's output paths."""
    studio = resolve(workspace)
    if not studio.saved:
        raise NotFoundError("save this workspace as a scene before "
                            "creating more")
    if not (slug := str(slug).strip()) or not slug.replace("-", "").replace("_", "").isalnum():
        raise ValidationError(["slug must be alphanumeric (-, _)"])
    if slug in [s.slug for s in studio.scenes]:
        raise ValidationError([f"scene {slug!r} already exists"])
    scene = studio.root / SCENES_DIR / slug
    scene.mkdir(parents=True)
    out = Path(seed_meta.get("still_dir", "")).parent
    text = SCAFFOLD.format(
        title=title or slug, comfy=seed_meta.get("comfy", "http://127.0.0.1:8188"),
        fps=seed_meta.get("fps", 24), frames=seed_meta.get("frames", 121),
        width=seed_meta.get("width", 768), height=seed_meta.get("height", 768),
        steps=seed_meta.get("steps", 20),
        still_dir=out / slug, reel_dir=out / f"{slug}_reel",
        final=out / f"{slug}_reel.mp4", work=scene / ".work")
    (scene / "reel.yaml").write_text(text)
    (scene / "assets.yaml").write_text("")
    updated = (Scene(slug, title or slug, f"{SCENES_DIR}/{slug}"),)
    _write(Studio(studio.root, studio.title, True,
                  studio.scenes + updated, slug))
    return scene


def view_of(workspace: str | Path) -> dict:
    """The studio read model: the scene registry."""
    studio = resolve(workspace)
    view = studio.view()
    view["workspace"] = str(studio.scene_dir)
    return view
