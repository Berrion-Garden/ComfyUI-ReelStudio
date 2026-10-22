"""The production narrative — one YAML file at the studio root.

`storyboard.yaml` sits beside studio.yaml, ABOVE the scenes: the
beat-by-beat story is production-level canon, not one scene's state. The
schema mirrors the original script's shape exactly — `style:`, then
ordered `acts:` (each with its music/sync note) of scene `checkpoints:`,
each checkpoint naming its `characters`/`locations` slugs and holding its
`shots:` (the script's Prompt N.M beats):

    style: High-quality, cinematic anime aesthetic…
    acts:
      - title: Act 1 — Waking Up to the Rhythm
        music: Synched to the opening guitar riff and buildup.
        checkpoints:
          - title: Scene 1 — The Antique Shop & Sarcophagus
            characters: [Amun]            # slugs — the UI renders links
            locations: [antique_shop_dawn]
            shots:
              - title: "1.1 Establishing Shot"
                text: Cinematic anime establishing shot…

Slug lists are EXPLICIT, never parsed out of the prose: they are the link
seam between the narrative and the digested YAML views (the
characters/locations blocks in the scene's reel.yaml).

One format, no legacy shapes: `view()` returns the doc NORMALIZED for
display — every act/checkpoint/shot carries all of its fields, so the UI
never sees a missing key. `save()` accepts that same normalized shape and
rejects the whole update on any structural error, naming the offender.

Ids for wiring: every checkpoint and shot carries an `id` the render
pipeline can reference (reel.yaml segments wire to a beat by id). The id
is DERIVED from the title's own numbering when not written explicitly
("Scene 1: …" → `scene-1`, "1.1 Establishing Shot" → `1.1`); an explicit
`id:` overrides it. Because save() round-trips the normalized doc, an id
once written is STABLE — renumbering a title does not move it, so the
render wiring never silently re-targets. Ids are unique across the doc.
Unknown keys anywhere in the doc are findings: the format is total, no
legacy shapes ride along.
"""

import re
from pathlib import Path

import yaml

from .errors import ValidationError

FILE = "storyboard.yaml"

_ACT_KEYS = {"title", "music", "checkpoints"}
_CHECKPOINT_KEYS = {"id", "title", "characters", "locations", "shots"}
_SHOT_KEYS = {"id", "title", "text"}
_DOC_KEYS = {"style", "acts"}


def _checkpoint_id(title: str, index: int) -> str:
    m = re.match(r"^Scene (\d+)", title)
    return f"scene-{m.group(1)}" if m else f"checkpoint-{index + 1}"


def _shot_id(title: str, index: int) -> str:
    m = re.match(r"^(\d+\.\d+)(?=[\s)（]|$)", title)
    return m.group(1) if m else f"shot-{index + 1}"


def path(root: Path) -> Path:
    return Path(root) / FILE


def _empty() -> dict:
    """The normalized shape every consumer can rely on."""
    return {"style": "", "acts": []}


def load(root: Path) -> dict:
    p = path(root)
    if not p.is_file():
        return _empty()
    doc = yaml.safe_load(p.read_text(encoding="utf-8"))
    return doc if isinstance(doc, dict) else _empty()


def normalize(doc: dict) -> dict:
    """Fill every field the display reads — the one shape, everywhere. Ids
    derive from the title's numbering when not written explicitly."""
    acts_out = []
    for act in (doc.get("acts") or []):
        checkpoints = []
        for ci, cp in enumerate(act.get("checkpoints") or []):
            shots = [{
                "id": shot.get("id")
                      or _shot_id(shot.get("title") or "", si),
                "title": shot.get("title") or "",
                "text": shot.get("text") or "",
            } for si, shot in enumerate(cp.get("shots") or [])]
            checkpoints.append({
                "id": cp.get("id")
                      or _checkpoint_id(cp.get("title") or "", ci),
                "title": cp.get("title") or "",
                "characters": list(cp.get("characters") or []),
                "locations": list(cp.get("locations") or []),
                "shots": shots})
        acts_out.append({"title": act.get("title") or "",
                         "music": act.get("music") or "",
                         "checkpoints": checkpoints})
    return {"style": doc.get("style") or "", "acts": acts_out}


def validate(doc: dict) -> list[str]:
    problems: list[str] = []

    def unknown_keys(spec: dict, where: str, allowed: set) -> None:
        extra = set(spec) - allowed
        if extra:
            problems.append(f"{where}: unknown keys {sorted(extra)} — "
                            f"allowed: {', '.join(sorted(allowed))}")

    def slugs(spec: dict, where: str, key: str) -> None:
        val = spec.get(key)
        if val is None:
            return
        if not isinstance(val, list) or \
                not all(isinstance(x, str) for x in val):
            problems.append(f"{where}: '{key}' must be a list of slugs")

    style = doc.get("style")
    if style is not None and not isinstance(style, str):
        problems.append("'style' must be a string")
    unknown_keys(doc, "document", _DOC_KEYS)

    acts = doc.get("acts")
    if not isinstance(acts, list):
        problems.append("'acts' must be a list")
        return problems
    ids: set[str] = set()
    for i, act in enumerate(acts):
        where = f"act {i + 1}"
        if not isinstance(act, dict):
            problems.append(f"{where}: must be a mapping")
            continue
        unknown_keys(act, where, _ACT_KEYS)
        title = act.get("title")
        if not isinstance(title, str) or not title:
            problems.append(f"{where}: missing 'title'")
        music = act.get("music")
        if music is not None and not isinstance(music, str):
            problems.append(f"{title!r}: 'music' must be a string")
        where = title or where
        checkpoints = act.get("checkpoints")
        if not isinstance(checkpoints, list):
            problems.append(f"{where}: 'checkpoints' must be a list")
            continue
        for j, cp in enumerate(checkpoints):
            cp_where = f"{where} checkpoint {j + 1}"
            if not isinstance(cp, dict):
                problems.append(f"{cp_where}: must be a mapping")
                continue
            unknown_keys(cp, cp_where, _CHECKPOINT_KEYS)
            cp_title = cp.get("title")
            if not isinstance(cp_title, str) or not cp_title:
                problems.append(f"{cp_where}: missing 'title'")
            cp_where = cp_title or cp_where
            if isinstance(cp.get("id"), str) and not cp["id"]:
                problems.append(f"{cp_where}: 'id' must not be empty")
            slugs(cp, cp_where, "characters")
            slugs(cp, cp_where, "locations")
            shots = cp.get("shots")
            if not isinstance(shots, list) or not shots:
                problems.append(f"{cp_where}: 'shots' must be a non-empty list")
                continue
            for k, shot in enumerate(shots):
                shot_where = f"{cp_where} shot {k + 1}"
                if not isinstance(shot, dict):
                    problems.append(f"{shot_where}: must be a mapping")
                    continue
                unknown_keys(shot, shot_where, _SHOT_KEYS)
                if isinstance(shot.get("id"), str) and not shot["id"]:
                    problems.append(f"{shot_where}: 'id' must not be empty")
                if not isinstance(shot.get("text"), str) or not shot["text"]:
                    problems.append(
                        f"{shot.get('title') or shot_where}: missing 'text'")

    doc_ids = normalize(doc)
    for cp in (c for a in doc_ids["acts"] for c in a["checkpoints"]):
        if cp["id"] in ids:
            problems.append(f"duplicate checkpoint id {cp['id']!r}")
        ids.add(cp["id"])
        for shot in cp["shots"]:
            if shot["id"] in ids:
                problems.append(f"duplicate shot id {shot['id']!r}")
            ids.add(shot["id"])
    return problems


def view(root: Path) -> dict:
    """What GET /narrative and the agent's get_narrative return: the
    normalized document plus where it lives."""
    root = Path(root)
    return {"path": str(path(root)), "doc": normalize(load(root))}


def save(root: Path, doc: dict) -> None:
    """Validate and write the whole narrative; the update is rejected on
    any structural error (mirrors project.save — the agent and the API
    both submit complete documents)."""
    if not isinstance(doc, dict):
        raise ValidationError(["narrative must be a mapping"])
    problems = validate(doc)
    if problems:
        raise ValidationError(problems)
    text = yaml.safe_dump(normalize(doc), sort_keys=False,
                          allow_unicode=True, width=76)
    p = path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
