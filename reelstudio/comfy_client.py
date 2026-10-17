"""ComfyUI HTTP client: submit graphs, poll history, stage inputs.

The only module that talks HTTP to ComfyUI (or to a fake server in tests).
Blocking on purpose — callers run it in a worker thread.
"""

import json
import subprocess
import time
import urllib.request
from pathlib import Path

FFMPEG = "/usr/bin/ffmpeg"


class ComfyError(RuntimeError):
    pass


class ComfyClient:
    def __init__(self, base_url: str, input_dir: str | Path, poll_s: float = 1.0,
                 timeout_s: float = 1800.0):
        self.base_url = base_url.rstrip("/")
        self.input_dir = Path(input_dir)
        self.poll_s = poll_s
        self.timeout_s = timeout_s

    # ------------------------------------------------------------ graph ----
    def submit(self, graph: dict, client_id: str = "reelstudio") -> str:
        body = json.dumps({"prompt": graph, "client_id": client_id}).encode()
        req = urllib.request.Request(
            self.base_url + "/prompt", data=body,
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.load(resp)["prompt_id"]

    def history(self, prompt_id: str) -> dict | None:
        with urllib.request.urlopen(
                f"{self.base_url}/history/{prompt_id}", timeout=120) as resp:
            return json.load(resp).get(prompt_id)

    def wait(self, prompt_id: str) -> dict:
        """Block until the job lands. Returns the history record.
        Raises ComfyError on execution failure or timeout."""
        deadline = time.time() + self.timeout_s
        while time.time() < deadline:
            rec = self.history(prompt_id)
            if rec:
                status = rec.get("status", {})
                if status.get("status_str") == "success":
                    return rec
                if status.get("status_str"):
                    raise ComfyError(
                        f"{prompt_id}: {status['status_str']} "
                        f"{status.get('messages', [])[-3:]}")
            time.sleep(self.poll_s)
        raise TimeoutError(f"{prompt_id}: not finished after {self.timeout_s}s")

    def submit_wait(self, graph: dict, client_id: str = "reelstudio") -> dict:
        prompt_id = self.submit(graph, client_id)
        return self.wait(prompt_id)

    # ------------------------------------------------------------ input ----
    def stage_input(self, name: str, src: str | Path) -> str:
        """Copy an anchor image into ComfyUI's input dir — always overwrite
        (Comfy caches inputs by filename, stale copies are worse than slow)."""
        self.input_dir.mkdir(parents=True, exist_ok=True)
        dst = self.input_dir / name
        subprocess.run(["cp", str(src), str(dst)], check=True)
        return name

    # ---------------------------------------------------------- snippets ---
    def extract_last_frame(self, clip: str | Path, out_png: str | Path) -> Path:
        subprocess.run(
            [FFMPEG, "-y", "-v", "error", "-sseof", "-0.05", "-i", str(clip),
             "-frames:v", "1", str(out_png)], check=True)
        return Path(out_png)
