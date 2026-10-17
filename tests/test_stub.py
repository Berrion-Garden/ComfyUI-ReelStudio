"""Stub backend: the full pipeline with zero network and no fake server.

Stub clips are real ffmpeg test-pattern videos, so prev_last extraction,
freeze post and assembly exercise the genuine code paths.
"""

import asyncio
import json
import subprocess


async def test_stub_render_chain_end_to_end(config, workspace, monkeypatch):
    from dataclasses import replace

    from reelstudio.app import create_app
    from aiohttp.test_utils import TestClient, TestServer

    cfg = replace(config, comfy_mode="stub")
    tc = TestClient(TestServer(create_app(cfg)))
    await tc.start_server()

    # the whole chain renders with NO comfy server bound to 8288
    resp = await tc.post("/reelstudio/api/render", json={"stale": True})
    assert resp.status == 200
    for _ in range(200):
        await asyncio.sleep(0.1)
        jobs = (await (await tc.get("/reelstudio/api/jobs")).json())["jobs"]
        if jobs and all(j["status"] in ("done", "error") for j in jobs):
            break
    assert all(j["status"] == "done" for j in jobs), jobs

    reel_dir = workspace / "output" / "reel"
    for sid in ("s1_ramen", "s2_bowldrop", "s3_pinkburst"):
        clips = list(reel_dir.glob(f"{sid}_*.mp4"))
        assert clips, f"{sid} stub deliverable missing"

    # stub clips are REAL videos: prev_last thumb extraction works
    resp = await tc.get("/reelstudio/api/scene/s2_bowldrop/artifact/thumb_first")
    assert resp.status == 200 and resp.headers["Content-Type"].startswith("image/png")

    # everything fresh in the project view
    data = await (await tc.get("/reelstudio/api/project")).json()
    assert data["comfy_mode"] == "stub"
    assert all(not s["stale"] for s in data["scenes"])

    # final production mixes the stub clips
    resp = await tc.post("/reelstudio/api/assemble", json={"use_music": False})
    for _ in range(200):
        await asyncio.sleep(0.1)
        jobs = (await (await tc.get("/reelstudio/api/jobs")).json())["jobs"]
        if jobs[-1]["kind"] == "assemble" and jobs[-1]["status"] in ("done", "error"):
            break
    assert jobs[-1]["status"] == "done", jobs[-1]
    probe = json.loads(subprocess.run(
        ["/usr/bin/ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "json", str(workspace / "output" / "final.mp4")],
        capture_output=True, check=True).stdout)
    assert abs(float(probe["format"]["duration"]) - data["total_s"]) < 0.5
    await tc.close()


async def test_stub_freeze_post(config, workspace):
    from dataclasses import replace

    from reelstudio.app import create_app
    from aiohttp.test_utils import TestClient, TestServer

    cfg = replace(config, comfy_mode="stub")
    tc = TestClient(TestServer(create_app(cfg)))
    await tc.start_server()
    resp = await tc.get("/reelstudio/api/yaml")
    text = (await resp.json())["text"].replace(
        "      soundscape: slurp",
        "      soundscape: slurp\n"
        "    post:\n"
        "      freeze:\n"
        "        at_s: 0.3\n"
        "        grade:\n"
        "          saturation: 1.6\n"
        "          contrast: 1.3")
    assert (await tc.put("/reelstudio/api/yaml", json={"text": text})).status == 200

    await tc.post("/reelstudio/api/render", json={"scene_ids": ["s1_ramen"]})
    for _ in range(200):
        await asyncio.sleep(0.1)
        jobs = (await (await tc.get("/reelstudio/api/jobs")).json())["jobs"]
        if jobs and all(j["status"] in ("done", "error") for j in jobs):
            break
    assert all(j["status"] == "done" for j in jobs), jobs
    assert list((workspace / "output" / "reel").glob("s1_ramen_9_freeze_*.mp4"))
    await tc.close()


async def test_stub_music_segment(config, workspace):
    from dataclasses import replace

    from reelstudio.app import create_app
    from aiohttp.test_utils import TestClient, TestServer

    cfg = replace(config, comfy_mode="stub")
    tc = TestClient(TestServer(create_app(cfg)))
    await tc.start_server()
    resp = await tc.get("/reelstudio/api/yaml")
    text = (await resp.json())["text"].replace(
        "    sound_effects:\n      soundscape: slurp",
        "    sound_effects:\n      soundscape: slurp\n    music:\n      name: opening\n      caption: rock")
    assert (await tc.put("/reelstudio/api/yaml", json={"text": text})).status == 200

    await tc.post("/reelstudio/api/music", json={"name": "opening"})
    for _ in range(200):
        await asyncio.sleep(0.1)
        jobs = (await (await tc.get("/reelstudio/api/jobs")).json())["jobs"]
        if jobs and all(j["status"] in ("done", "error") for j in jobs):
            break
    assert all(j["status"] == "done" for j in jobs), jobs
    assert list((workspace / "output" / "reel").glob("music_opening_*.wav"))
    await tc.close()

