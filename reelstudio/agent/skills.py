"""Skill loading for the chat agent.

Skills live in the repo's skills/ directory (open Agent Skills format:
frontmatter name/description + markdown body). They are injected whole into
the agent's system prompt — the agent is the primary consumer, and the same
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
    """All skills in the directory: {name, description, body, path}.
    Sorted by name for a stable prompt."""
    d = dir_path or skills_dir()
    if not d.is_dir():
        return []
    out = []
    for path in sorted(d.glob("*.md")):
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
        })
    return out


def render_skills_block(loaded: list[dict]) -> str:
    if not loaded:
        return ""
    sections = [
        f"## Skill: {s['name']}\n{s['body']}" for s in loaded
    ]
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
