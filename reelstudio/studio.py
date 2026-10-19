"""The studio wrapper — one YAML layer above reel.yaml.

A studio is a directory holding `studio.yaml` (the registry of scenes) and
one shared `reel.py` (the pipeline — never duplicated). Each scene is a
self-contained directory under `scenes/` (reel.yaml, assets.yaml, and the
asset libraries). `resolve()` accepts the root OR any scene dir as the
configured workspace; an unmigrated workspace is an implicit one-scene
studio that `save_as()` turns into the real nested structure.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import re
import shutil

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
locations:
  open_plate:
    pro: the opening environment for this narrative, held in one frame
    con: blank void, placeholder text, watermark
stills: {{}}

scenes:
  - id: s1_open
    next: null
    location: open_plate
    video:
      mode: i2v
      first: null
      last: null
      description: |
        Describe the action of the opening beat here — one narrative chunk.
"""


def _slugify(name: str) -> str:
    s = name.lower().replace("'", "").replace("’", "")
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_")


def create_scene(workspace: str | Path, title: str, seed_meta: dict) -> Path:
    """Scaffold a fresh, valid scene directory and make it current. The slug
    is never supplied: title snake_cased + a timestamp — no collisions, no
    naming burden. seed_meta is the current scene's reel.yaml meta — the
    template for the render defaults and the parent dir of the new scene's
    output paths."""
    studio = resolve(workspace)
    if not studio.saved:
        raise NotFoundError("save this workspace as a scene before "
                            "creating more")
    base = _slugify(str(title or "").strip())
    if not base:
        raise ValidationError(["a scene needs a name"])
    slug = f"{base}_{datetime.now():%Y%m%d_%H%M%S}"
    scene = studio.root / SCENES_DIR / slug
    scene.mkdir(parents=True)
    out = Path(seed_meta.get("still_dir", "")).parent
    text = SCAFFOLD.format(
        title=title, comfy=seed_meta.get("comfy", "http://127.0.0.1:8188"),
        fps=seed_meta.get("fps", 24), frames=seed_meta.get("frames", 121),
        width=seed_meta.get("width", 768), height=seed_meta.get("height", 768),
        steps=seed_meta.get("steps", 20),
        still_dir=out / slug, reel_dir=out / f"{slug}_reel",
        final=out / f"{slug}_reel.mp4", work=scene / ".work")
    (scene / "reel.yaml").write_text(text)
    (scene / "assets.yaml").write_text("")
    updated = (Scene(slug, title, f"{SCENES_DIR}/{slug}"),)
    _write(Studio(studio.root, studio.title, True,
                  studio.scenes + updated, slug))
    return scene


def view_of(workspace: str | Path) -> dict:
    """The studio read model: the registry plus each scene's character and
    location pools — what the import pickers offer."""
    studio = resolve(workspace)

    def pools(d: Path) -> list[str]:
        return sorted(p.name for p in d.iterdir() if p.is_dir()) \
            if d.is_dir() else []

    def extra(scene) -> dict:
        d = studio.dir_of(scene.slug)
        return {"characters": pools(d / "characters"),
                "backgrounds": pools(d / "backgrounds")}

    view = studio.view(extra)
    view["workspace"] = str(studio.scene_dir)
    return view


def import_assets(workspace: str | Path, from_slug: str,
                  characters: Iterable[str] = (),
                  backgrounds: Iterable[str] = (),
                  as_name: str | None = None) -> dict:
    """Copy character/location pools from another scene into the CURRENT
    one. A pool lands under its own name, or — single-pool imports — under
    `as_name`, merging into an existing pool file-by-file, never clobbering.
    Declared labels come along (scene:* foreign keys stripped, paths
    re-keyed to the destination)."""
    studio = resolve(workspace)
    if not studio.saved:
        raise NotFoundError("importing needs a saved scene registry")
    src_dir = studio.dir_of(from_slug)
    dst_dir = studio.scene_dir
    if src_dir == dst_dir:
        raise ValidationError(["cannot import a scene into itself"])
    src_labels = _declared_labels(src_dir)

    requested = [("characters", list(characters)),
                 ("backgrounds", list(backgrounds))]
    total = sum(len(names) for _, names in requested)
    imported, labels = [], {}
    for kind, names in requested:
        for name in names:
            name = str(name).strip()
            src = src_dir / kind / name
            if not src.is_dir():
                raise NotFoundError(f"{from_slug} has no pool "
                                    f"{kind}/{name!r}")
            dst_name = (str(as_name).strip() or name) \
                if total == 1 else name
            dst = dst_dir / kind / dst_name
            for f in sorted(p for p in src.rglob("*") if p.is_file()):
                target = dst / f.relative_to(src)
                if target.exists():
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, target)
                imported.append(target.relative_to(dst_dir).as_posix())
                src_rel = f.relative_to(src_dir).as_posix()
                if src_rel in src_labels:
                    labels[imported[-1]] = _clean_labels(src_labels[src_rel])
    if labels:
        _merge_labels(dst_dir, labels)
    return {"from": from_slug, "imported": sorted(imported)}


def _declared_labels(scene_dir: Path) -> dict[str, list[str]]:
    f = scene_dir / "assets.yaml"
    if not f.is_file():
        return {}
    doc = yaml.safe_load(f.read_text()) or {}
    return {str(k): list(v) for k, v in (doc.get("labels") or {}).items()}


def _clean_labels(labels: list[str]) -> list[str]:
    return [l for l in labels if not l.startswith("scene:")]


def _merge_labels(scene_dir: Path, extra: dict[str, list[str]]) -> None:
    f = scene_dir / "assets.yaml"
    doc = yaml.safe_load(f.read_text()) if f.is_file() else {}
    labels = {str(k): list(v)
              for k, v in (doc or {}).get("labels", {}).items()}
    labels.update(extra)
    f.write_text(yaml.safe_dump({"labels": labels}, sort_keys=False))
