"""Runtime configuration.

Precedence: environment variables -> config file (~/.config/reelstudio/config.json)
-> defaults. The workspace (holding reel.yaml + reel.py) is the only pipeline
location; there is no direct ComfyUI/ffmpeg config — reel.py owns that.
"""

import json
import os
from dataclasses import dataclass
from pathlib import Path

CONFIG_FILE = Path(os.environ.get("REELSTUDIO_CONFIG", "~/.config/reelstudio/config.json")).expanduser()


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


def load_config(env: dict | None = None) -> Config:
    e = dict(os.environ) if env is None else env
    file_cfg = {}
    if CONFIG_FILE.exists():
        file_cfg = json.loads(CONFIG_FILE.read_text())

    def get(key: str, default):
        return e.get(f"REELSTUDIO_{key.upper()}", file_cfg.get(key, default))

    return Config(
        workspace=Path(get("workspace", Path(__file__).resolve().parent.parent / "workspace")),
        agent_model=str(get("agent_model", "writer")),
        agent_base_url=str(get("agent_base_url", "https://llms.berrion.garden/v1")),
    )
