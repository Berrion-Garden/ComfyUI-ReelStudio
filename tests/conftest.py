"""Shared fixtures.

The pipeline is the workspace's reel.py, executed as a subprocess — tests
never touch the live GPU node. The fixture workspace ships a STUB reel.py
with the same CLI that writes real (tiny) deliverables, so jobs, manifest
recording and staleness run the real orchestration path end to end.
"""

import subprocess
from pathlib import Path

import pytest
import yaml

from reelstudio.app import create_app
from reelstudio.config import Config

FFMPEG = "/usr/bin/ffmpeg"

YAML_BODY = """
meta:
  comfy: {comfy}
  fps: 24
  frames: 22
  width: 160
  height: 160
  steps: 4
  still_dir: {workspace}/stills
  reel_dir: {workspace}/output/reel
  final: {workspace}/output/final.mp4
  work: {workspace}/.work

aliases:
  fox: the pink fox boy

stills:
  opening: opening_still
  impact: impact_still
  end: end_still

scenes:
  - id: s1_ramen
    next: s2_bowldrop
    video:
      mode: i2v
      first: still:opening
      last: null
      description: |
        The fox eats noodles. {{fox}}.
      negative: text, watermark
    sound_effects:
      soundscape: slurp

  - id: s2_bowldrop
    next: s3_pinkburst
    video:
      mode: i2v
      first: prev_last
      last: null
      description: |
        The fox drops the bowl. {{fox}}.
    sound_effects:
      soundscape: clatter

  - id: s3_pinkburst
    next: null
    video:
      mode: fl2v
      first: still:impact
      last: still:end
      description: |
        Pink explosion. {{fox}}.
"""

# Same CLI contract as the real reel.py: render <id...>, music, assemble,
# bell [out]. Deliverables are tiny real files so serving/staleness work.
STUB_REEL_PY = '''
#!/usr/bin/env python3
"""Test double for the workspace pipeline: same CLI, no ComfyUI."""
import os
import subprocess
import sys

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = yaml.safe_load(open(os.path.join(HERE, "reel.yaml")))
M = CFG["meta"]
FF = "/usr/bin/ffmpeg"


def _tiny(path, ext):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if ext == "mp4":
        args = [FF, "-y", "-v", "error", "-f", "lavfi",
                "-i", "color=c=red:s=64x64:r=8:d=0.5",
                "-f", "lavfi", "-i", "sine=frequency=440:duration=0.5",
                "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-c:a", "aac"]
    else:
        args = [FF, "-y", "-v", "error", "-f", "lavfi",
                "-i", "sine=frequency=440:duration=0.5",
                "-c:a", "pcm_s16le"]
    subprocess.run(args + [path], check=True)


def _run(argv):
    cmd = argv[0]
    if cmd == "render":
        for sid in argv[1:]:
            _tiny(os.path.join(M["reel_dir"], f"{sid}_00001_.mp4"), "mp4")
    elif cmd == "music":
        for s in CFG["scenes"]:
            m = s.get("music")
            if isinstance(m, dict):
                _tiny(os.path.join(M["reel_dir"],
                                   f"music_{m['name']}_00001_.wav"), "wav")
    elif cmd == "assemble":
        _tiny(M["final"], "mp4")
    elif cmd == "bell":
        out = argv[1] if len(argv) > 1 else os.path.join(M["work"], "bell.wav")
        _tiny(out, "wav")
    else:
        raise SystemExit(f"stub reel.py: unknown command {cmd!r}")


if __name__ == "__main__":
    _run(sys.argv[1:])
'''


def make_still(path: Path, color: str = "blue") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([FFMPEG, "-y", "-v", "error", "-f", "lavfi",
                    "-i", f"color=c={color}:s=64x64", "-frames:v", "1",
                    str(path)], check=True)
    return path


def write_stub_reel(workspace: Path) -> Path:
    script = workspace / "reel.py"
    script.write_text(STUB_REEL_PY)
    script.chmod(0o755)
    return script


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "workspace"
    ws.mkdir()
    for name, color in (("opening_still_.png", "blue"),
                        ("impact_still_.png", "green"),
                        ("end_still_.png", "purple")):
        make_still(ws / "stills" / name, color)
    (ws / "reel.yaml").write_text(
        YAML_BODY.format(comfy="http://127.0.0.1:9", workspace=ws))
    write_stub_reel(ws)
    return ws


def make_config(ws: Path) -> Config:
    return Config(
        workspace=ws,
        agent_model="orchestrator",
        agent_base_url="https://llms.berrion.garden/v1",
    )


@pytest.fixture
def config(workspace: Path) -> Config:
    return make_config(workspace)


@pytest.fixture
async def client(config: Config):
    from aiohttp.test_utils import TestClient, TestServer

    app = create_app(config)
    tc = TestClient(TestServer(app))
    await tc.start_server()
    yield tc
    await tc.close()


def wait_for_jobs(client, timeout: float = 60.0):
    """Poll until every job left the queue. Returns the final jobs list."""
    import asyncio

    async def poll():
        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            resp = await client.get("/reelstudio/api/jobs")
            jobs = (await resp.json())["jobs"]
            if jobs and all(j["status"] in ("done", "error") for j in jobs):
                return jobs
            await asyncio.sleep(0.2)
        return jobs

    return poll()
