"""Skill loading for the chat agent.

Skills live in the repo's skills/ directory (open Agent Skills format:
frontmatter name/description + markdown body). A skill's own frontmatter
decides how it loads: `always: true` skills are injected whole into the
system prompt (the editing spine the agent needs every turn); the rest are
advertised as an index and pulled on demand with the agent's `get_skill`
tool — deep vocabulary is a roundtrip, not always-on context. The same
files document the pipeline for human readers and coding agents.
"""

import os
from pathlib import Path

import yaml

from ..errors import ReelStudioError

DEFAULT_SKILLS_DIR = Path(__file__).resolve().parent.parent.parent / "skills"


def skills_dir() -> Path:
    override = os.environ.get("REELSTUDIO_SKILLS_DIR")
    return Path(override) if override else DEFAULT_SKILLS_DIR


def load_skills(dir_path: Path | None = None) -> list[dict]:
    """All skills in the directory: {name, description, body, path, always}.
    Sorted by name for a stable prompt."""
    d = dir_path or skills_dir()
    if not d.is_dir():
        return []
    out = []
    # top-level skills plus one-dir-per-skill packages (skills/<name>/SKILL.md,
    # the open Agent Skills layout)
    paths = sorted([*d.glob("*.md"), *d.glob("*/SKILL.md")])
    for path in paths:
        text = path.read_text()
        meta: dict = {}
        body = text
        if text.startswith("---"):
            parts = text.split("---", 2)
            if len(parts) == 3:
                meta = yaml.safe_load(parts[1]) or {}
                body = parts[2].strip()
        out.append({
            "name": meta.get("name", path.stem),
            "description": meta.get("description", ""),
            "body": body,
            "path": str(path),
            "always": bool(meta.get("always")),
        })
    return out


def render_skills_block(loaded: list[dict]) -> str:
    """Always-on skills whole; the rest as a one-line index. The agent loads
    the rest with get_skill when a task matches its description."""
    sections = [
        f"## Skill: {s['name']}\n{s['body']}" for s in loaded if s["always"]
    ]
    on_demand = [s for s in loaded if not s["always"]]
    if on_demand:
        index = "\n".join(f"- {s['name']} — {s['description']}"
                          for s in on_demand)
        sections.append(
            "# Skills on demand (get_skill <name>)\n\n" + index)
    return "\n\n".join(sections)


def system_prompt(base: str, dir_path: Path | None = None) -> str:
    """Base system prompt with every skill injected. A missing skills dir is
    an error only in production — tests pass explicit dirs."""
    loaded = load_skills(dir_path)
    if dir_path is not None and not loaded:
        raise ReelStudioError(f"no skills found in {dir_path}")
    block = render_skills_block(loaded)
    if not block:
        return base
    return f"{base}\n\n# Skills\n\n{block}"
