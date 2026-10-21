"""The production narrative — one YAML file at the studio root.

`storyboard.yaml` sits beside studio.yaml, ABOVE the scenes: the
checkpoint-by-checkpoint story is production-level canon, not one scene's
state. The schema mirrors the storyboard a creator writes by hand —
`style:` + ordered `acts:`, each holding sync/music notes and its
`checkpoints:` (the shot beats):

    style: High-quality, cinematic anime aesthetic…
    acts:
      - title: Act 1 — Waking Up to the Rhythm
        music: Synched to the opening guitar riff and buildup.
        checkpoints:
          - title: Scene 1 — The Antique Shop & Sarcophagus
            text: |
              Prompt 1.1 (Establishing Shot): …
            characters: [amunrekh]   # slugs — the UI renders them as links
            locations: [antique_shop]

`characters`/`locations` are EXPLICIT slug lists, never parsed out of the
prose: they are the link seam between the narrative and the digested YAML
views (characters/locations blocks in the scene's reel.yaml).

`load` returns a default (empty acts) when the file does not exist yet —
a production starts its narrative before anything is saved. `save`
validates first and writes the whole document; validation failures name
the offending act/checkpoint so the agent can self-correct.
"""

from pathlib import Path

import yaml

from .errors import ValidationError

FILE = "storyboard.yaml"


def path(root: Path) -> Path:
    return Path(root) / FILE


def _default() -> dict:
    return {"style": "", "acts": []}


def load(root: Path) -> dict:
    p = path(root)
    if not p.is_file():
        return _default()
    doc = yaml.safe_load(p.read_text(encoding="utf-8"))
    return doc if isinstance(doc, dict) else _default()


def validate(doc: dict) -> list[str]:
    problems: list[str] = []

    def strings(spec: dict, where: str, key: str) -> None:
        val = spec.get(key)
        if val is None:
            return
        if not isinstance(val, list) or \
                not all(isinstance(x, str) for x in val):
            problems.append(f"{where}: '{key}' must be a list of slugs")

    style = doc.get("style")
    if style is not None and not isinstance(style, str):
        problems.append("'style' must be a string")

    acts = doc.get("acts")
    if not isinstance(acts, list):
        problems.append("'acts' must be a list")
        return problems
    for i, act in enumerate(acts):
        where = f"act {i + 1}"
        if not isinstance(act, dict):
            problems.append(f"{where}: must be a mapping")
            continue
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
            cp_title = cp.get("title")
            if not isinstance(cp_title, str) or not cp_title:
                problems.append(f"{cp_where}: missing 'title'")
            if not isinstance(cp.get("text"), str) or not cp["text"]:
                problems.append(f"{cp_title or cp_where}: missing 'text'")
            for key in ("characters", "locations"):
                strings(cp, cp_title or cp_where, key)
    return problems


def view(root: Path) -> dict:
    """What GET /narrative and the agent's get_narrative return."""
    root = Path(root)
    doc = load(root)
    return {"path": str(path(root)), "style": doc.get("style"),
            "acts": doc.get("acts", [])}


def save(root: Path, text: str) -> None:
    """Validate and write the whole narrative; the update is rejected on
    any structural error (mirrors project.save — the agent and the API
    both submit complete files)."""
    if not isinstance(text, str) or not text.strip():
        raise ValidationError(["narrative text required"])
    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise ValidationError([f"yaml error: {e}"]) from e
    if not isinstance(doc, dict):
        raise ValidationError(["narrative must be a mapping"])
    problems = validate(doc)
    if problems:
        raise ValidationError(problems)
    p = path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
