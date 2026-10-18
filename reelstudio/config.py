"""Runtime configuration.

Precedence: environment variables -> .env file -> config file
(~/.config/reelstudio/config.json) -> defaults. The workspace (holding
reel.yaml + reel.py) is the only pipeline location; there is no direct
ComfyUI/ffmpeg config — reel.py owns that. The variable list lives in
.env.example; the deploy story in docs/deployment.md.
"""

import json
import os
from dataclasses import dataclass
from pathlib import Path

CONFIG_FILE = Path(os.environ.get("REELSTUDIO_CONFIG", "~/.config/reelstudio/config.json")).expanduser()
ENV_FILE = Path(os.environ.get("REELSTUDIO_ENV",
                               Path(__file__).resolve().parent.parent / ".env"))


@dataclass(frozen=True)
class Config:
    workspace: Path          # directory holding reel.yaml AND reel.py
    agent_model: str         # chat agent model alias on the gateway
    agent_base_url: str      # OpenAI-compatible gateway base URL

    @property
    def yaml_path(self) -> Path:
        return self.workspace / "reel.yaml"

    @property
    def work_dir(self) -> Path:
        return self.workspace / ".work"


def _env_file_values(path: Path) -> dict[str, str]:
    """KEY=VALUE lines from a .env file. Real environment variables win, so
    these seed only what the environment does not already set."""
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.removeprefix("export ").partition("=")
        values[key.strip()] = value.strip().strip("\"'")
    return values


def load_config(env: dict | None = None) -> Config:
    """With no explicit env dict, the process environment is layered over
    the .env file. Passing a dict (tests, embedders) is full control — the
    .env file is not consulted."""
    e = dict(os.environ) if env is None else env
    env_file = _env_file_values(ENV_FILE) if env is None else {}
    if CONFIG_FILE.exists():
        file_cfg = json.loads(CONFIG_FILE.read_text())
    else:
        file_cfg = {}

    def get(key: str, default):
        prefixed = f"REELSTUDIO_{key.upper()}"
        return (e.get(prefixed) or env_file.get(prefixed)
                or file_cfg.get(key, default))

    return Config(
        workspace=Path(get("workspace", Path(__file__).resolve().parent.parent / "workspace")),
        agent_model=str(get("agent_model", "writer")),
        agent_base_url=str(get("agent_base_url", "https://llms.berrion.garden/v1")),
    )
