"""Shared fixtures.

The fake ComfyUI binds the isolated test endpoint 127.0.0.1:8288 (see
reelstudio.config.TEST_COMFY_URL) so integration never touches the live GPU
node on 8188. Tiny real videos are rendered with ffmpeg — prev_last frame
extraction and final assembly run the real code path end to end.
"""

import subprocess
from pathlib import Path

import pytest
import yaml
from aiohttp import web

from reelstudio.app import create_app
from reelstudio.config import TEST_COMFY_URL, Config

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
  work: {workspace}/work

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


def make_tiny_video(path: Path, color: str = "red") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [FFMPEG, "-y", "-v", "error", "-f", "lavfi",
         "-i", f"color=c={color}:s=160x160:r=24:d=1", "-f", "lavfi",
         "-i", "anullsrc=r=44100:cl=stereo", "-shortest", "-c:v", "libx264",
         "-pix_fmt", "yuv420p", "-c:a", "aac", str(path)], check=True)
    return path


def make_still(path: Path, color: str = "blue") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([FFMPEG, "-y", "-v", "error", "-f", "lavfi",
                    "-i", f"color=c={color}:s=64x64", "-frames:v", "1",
                    str(path)], check=True)
    return path


def fake_comfy_app(output_dir: Path) -> tuple[web.Application, dict]:
    """Mimics the pieces of ComfyUI the pipeline touches: /prompt executes
    synchronously (writes the deliverable like SaveVideo/SaveAudio would),
    /history reports success."""
    state = {"graphs": [], "n": 0, "history": {}}

    def execute(graph: dict) -> dict:
        outputs = {}
        for node_id, node in graph.items():
            ct = node["class_type"]
            if ct in ("SaveVideo", "SaveAudio"):
                prefix = node["inputs"]["filename_prefix"]
                target = output_dir / f"{prefix}_00001_.{'mp4' if ct == 'SaveVideo' else 'wav'}"
                if ct == "SaveVideo":
                    make_tiny_video(target)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    subprocess.run([FFMPEG, "-y", "-v", "error", "-f", "lavfi",
                                    "-i", "sine=frequency=440:duration=1",
                                    str(target)], check=True)
                outputs[node_id] = {}
        return outputs

    async def prompt(request: web.Request) -> web.Response:
        body = await request.json()
        graph = body["prompt"]
        state["graphs"].append(graph)
        state["n"] += 1
        pid = f"fake-{state['n']:04d}"
        state["history"][pid] = {
            "status": {"status_str": "success"},
            "outputs": execute(graph),
        }
        return web.json_response({"prompt_id": pid})

    async def history(request: web.Request) -> web.Response:
        return web.json_response(
            {request.match_info["pid"]: state["history"].get(request.match_info["pid"])})

    app = web.Application()
    app.router.add_post("/prompt", prompt)
    app.router.add_get("/history/{pid}", history)
    return app, state


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "workspace"
    ws.mkdir()
    for name, color in (("opening_still_.png", "blue"),
                        ("impact_still_.png", "green"),
                        ("end_still_.png", "purple")):
        make_still(ws / "stills" / name, color)
    (ws / "reel.yaml").write_text(YAML_BODY.format(comfy=TEST_COMFY_URL, workspace=ws))
    return ws


def make_config(ws: Path) -> Config:
    return Config(
        workspace=ws,
        comfy_url=TEST_COMFY_URL,
        comfy_input_dir=ws / "input",
        agent_model="orchestrator",
        agent_base_url="https://llms.berrion.garden/v1",
    )


@pytest.fixture
def config(workspace: Path) -> Config:
    return make_config(workspace)


@pytest.fixture
async def fake_comfy(workspace: Path):
    app, state = fake_comfy_app(workspace / "output")
    from aiohttp.test_utils import TestServer

    # the isolated endpoint: same port the real test config points at
    server = TestServer(app, host="127.0.0.1", port=8288)
    await server.start_server()
    yield state
    await server.close()


@pytest.fixture
async def client(config: Config, fake_comfy):
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
