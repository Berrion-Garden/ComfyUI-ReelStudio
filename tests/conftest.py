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

styles:
  anime:
    pro: 2D anime, cel-shaded, clean bold line art, vibrant flat colors
    con: photorealistic, 3D rendering, live action, text, watermark
  pixar:
    pro: 3D animation, soft global illumination, expressive stylized characters
    con: flat 2D, sketchy lines
style: anime

locations:
  campus_sunset:
    pro: university campus plaza at golden sunset, warm orange sky
    con: indoor, night, rain
  campus_dawn:
    pro: the campus at first light, cool blue dawn sky
    con: indoors, night, crowds

stills:
  opening: null
  impact: null
  end: null

scenes:
  - id: s1_ramen
    next: s2_bowldrop
    location: campus_sunset
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
    location: campus_dawn
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
    location: campus_dawn
    video:
      mode: i2v
      first: still:impact
      last: still:end
      description: |
        Pink explosion. {{fox}}.
"""

# Same CLI contract as the real reel.py: render <id...>, music, assemble,
# bell [out], collapse. Deliverables are tiny real files so serving/staleness
# works; collapse emits the merged generation input exactly like the contract
# the app caches and diffs.
STUB_REEL_PY = r'''
#!/usr/bin/env python3
"""Test double for the workspace pipeline: same CLI, no ComfyUI."""
import os
import subprocess
import sys

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
# Same scene contract as the real reel.py: the scene is the cwd when it
# holds reel.yaml (the studio runs the shared script from the scene dir).
SCENE = os.getcwd() if os.path.isfile(os.path.join(os.getcwd(), "reel.yaml")) else HERE
CFG = yaml.safe_load(open(os.path.join(SCENE, "reel.yaml")))
M = CFG["meta"]
FF = "/usr/bin/ffmpeg"


def _tiny(path, ext, shade=0):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if ext == "mp4":
        args = [FF, "-y", "-v", "error", "-f", "lavfi",
                "-i", f"color=c=0x{0x20 + shade:02d}5588:s=64x64:r=8:d=0.5",
                "-f", "lavfi", "-i", "sine=frequency=440:duration=0.5",
                "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-c:a", "aac"]
    else:
        args = [FF, "-y", "-v", "error", "-f", "lavfi",
                "-i", "sine=frequency=440:duration=0.5",
                "-c:a", "pcm_s16le"]
    subprocess.run(args + [path], check=True)


def fh(path):
    import hashlib
    try:
        return hashlib.sha256(open(path, "rb").read()).hexdigest()[:16]
    except OSError:
        return "missing"


def _anchor(ref, prev_sid):
    if ref in (None, "", "null"):
        return {"kind": "none"}
    if ref == "prev_last":
        import glob
        hits = sorted(glob.glob(os.path.join(M["reel_dir"], f"{prev_sid}_*.mp4")))
        return {"kind": "prev_last", "file_hash": fh(hits[-1] if hits else "")}
    if ref.startswith("still:"):
        p = os.path.join(M["still_dir"], ref[6:] + "_.png")
        return {"kind": "still", "path": p, "file_hash": fh(p)}


def _collapse():
    import json
    al = CFG.get("aliases", {})
    style = (CFG.get("styles") or {}).get(CFG.get("style") or "", {})
    ids = [s["id"] for s in CFG["scenes"]]
    out = {}
    for i, s in enumerate(CFG["scenes"]):
        loc = (CFG.get("locations") or {}).get(s.get("location") or "", {})
        v = s["video"]
        parts = [b["pro"].format(**al) for b in (style, loc) if b.get("pro")]
        parts.append(v["description"].strip().format(**al))
        merged_neg = ", ".join(dict.fromkeys(
            t.strip() for src in ((v.get("negative") or ""),
                                  (style.get("con") or ""),
                                  (loc.get("con") or ""))
            for t in src.split(",") if t.strip()))
        out[s["id"]] = {
            "prompt": "\n".join(parts),
            "negative": merged_neg,
            "frames": s.get("frames", M["frames"]),
            "mode": v.get("mode"),
            "first": _anchor(v.get("first"), ids[i - 1] if i else None),
            "last": _anchor(v.get("last"), ids[i - 1] if i else None),
            "size": [M["width"], M["height"]],
            "steps": M["steps"],
        }
    return json.dumps({"scenes": out})


def _run(argv):
    cmd = argv[0]
    if cmd == "render":
        import glob
        for sid in argv[1:]:
            # real SaveVideo increments the suffix; re-renders change the file
            n = len(glob.glob(os.path.join(M["reel_dir"], f"{sid}_*.mp4"))) + 1
            _tiny(os.path.join(M["reel_dir"], f"{sid}_{n:05d}_.mp4"), "mp4",
                  shade=n)
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
    elif cmd == "collapse":
        print(_collapse())
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
    for name, color in (("opening_.png", "blue"),
                        ("impact_.png", "green"),
                        ("end_.png", "purple")):
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
