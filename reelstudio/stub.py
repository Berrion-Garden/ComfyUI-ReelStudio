"""Stub ComfyUI backend: executes render graphs locally with ffmpeg.

Same seam as the real client (submit_wait / stage_input / extract_last_frame),
no network, seconds instead of minutes. It writes deliverables exactly where
SaveVideo/SaveAudio would — same filenames, same dir — so deliverable lookup,
manifests, prev_last extraction, freeze post and assembly all run the real
code path. For testing the flow ONLY: stub clips are test patterns, not
delivery.
"""

import subprocess
from pathlib import Path

from .comfy_client import ComfyClient, FFMPEG


class StubComfyClient(ComfyClient):
    def __init__(self, reel_dir: str | Path, input_dir: str | Path):
        super().__init__(base_url="stub://local", input_dir=input_dir,
                         timeout_s=60.0)
        self.reel_dir = Path(reel_dir)

    def submit_wait(self, graph: dict, client_id: str = "reelstudio") -> dict:
        self.reel_dir.mkdir(parents=True, exist_ok=True)
        for node in graph.values():
            ct = node["class_type"]
            if ct == "SaveVideo":
                self._write_video(graph)
            elif ct == "SaveAudio":
                self._write_audio(graph)
        return {"status": {"status_str": "success"}, "outputs": {}}

    def _inputs(self, graph: dict, class_type: str) -> dict:
        for node in graph.values():
            if node["class_type"] == class_type:
                return node["inputs"]
        return {}

    def _write_video(self, graph: dict) -> None:
        prefix = self._inputs(graph, "SaveVideo")["filename_prefix"]
        create = self._inputs(graph, "CreateVideo")
        fps = float(create.get("fps", 24.0))
        h3 = self._inputs(graph, "MiniMaxH3ImageToVideo")
        frames = int(h3.get("length", int(fps)))
        w = int(h3.get("width", 160))
        h = int(h3.get("height", 160))
        out = self.reel_dir / f"{Path(prefix).name}_00001_.mp4"
        subprocess.run(
            [FFMPEG, "-y", "-v", "error",
             "-f", "lavfi", "-i",
             f"testsrc2=s={w}x{h}:r={fps:g}:d={frames / fps:.4f}",
             "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
             "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p",
             "-c:a", "aac", str(out)], check=True)

    def _write_audio(self, graph: dict) -> None:
        prefix = self._inputs(graph, "SaveAudio")["filename_prefix"]
        latent = self._inputs(graph, "EmptyMiniMaxMusic3LatentAudio")
        seconds = float(latent.get("seconds", 5.0))
        out = self.reel_dir / f"{Path(prefix).name}_00001_.wav"
        subprocess.run(
            [FFMPEG, "-y", "-v", "error", "-f", "lavfi",
             "-i", f"sine=frequency=440:duration={seconds:.2f}",
             str(out)], check=True)
