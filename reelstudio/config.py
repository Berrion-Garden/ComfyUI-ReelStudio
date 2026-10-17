"""Runtime configuration.

Precedence: environment variables -> config file (~/.config/reelstudio/config.json)
-> defaults. The ComfyUI endpoint is always overridable so tests and worktree
instances can run against an isolated fake server instead of the live GPU node.
"""

import json
import os
from dataclasses import dataclass
from pathlib import Path

CONFIG_FILE = Path(os.environ.get("REELSTUDIO_CONFIG", "~/.config/reelstudio/config.json")).expanduser()

DEFAULT_COMFY_URL = "http://localhost:8188"
# Port 8288 is the designated isolated test endpoint: fake ComfyUI instances
# bind here so worktree integration never touches the live node on 8188.
TEST_COMFY_URL = os.environ.get("REELSTUDIO_TEST_COMFY_URL", "http://127.0.0.1:8288")


@dataclass(frozen=True)
class Config:
    workspace: Path          # directory holding reel.yaml
    comfy_url: str           # ComfyUI HTTP endpoint (/prompt, /history)
    comfy_input_dir: Path    # ComfyUI's input dir for staged anchor images
    agent_model: str         # chat agent model alias on the gateway
    agent_base_url: str      # OpenAI-compatible gateway base URL
    comfy_mode: str = "live"  # "live" (HTTP to comfy_url) | "stub" (local ffmpeg)

    @property
    def yaml_path(self) -> Path:
        return self.workspace / "reel.yaml"


def load_config(env: dict | None = None) -> Config:
    e = dict(os.environ) if env is None else env
    file_cfg = {}
    if CONFIG_FILE.exists():
        file_cfg = json.loads(CONFIG_FILE.read_text())

    def get(key: str, default):
        return e.get(f"REELSTUDIO_{key.upper()}", file_cfg.get(key, default))

    workspace = Path(get("workspace", Path(__file__).resolve().parent.parent / "workspace"))
    comfy_url = get("comfy_url", DEFAULT_COMFY_URL)
    input_dir = get("comfy_input_dir", None)
    if input_dir is None:
        # Sibling of the workspace's output tree when not configured explicitly.
        input_dir = workspace / "input"
    return Config(
        workspace=workspace,
        comfy_url=str(comfy_url),
        comfy_input_dir=Path(input_dir),
        agent_model=str(get("agent_model", "orchestrator")),
        agent_base_url=str(get("agent_base_url", "https://llms.berrion.garden/v1")),
        comfy_mode=str(get("comfy_mode", "live")),
    )
