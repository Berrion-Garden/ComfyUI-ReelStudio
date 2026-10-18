"""Orchestration integration: jobs run the workspace's reel.py subprocess and
the manifest vouches for what it produced. Real files, no ComfyUI."""

import json
import subprocess

from conftest import wait_for_jobs


async def test_project_view_starts_fully_stale(client):
    resp = await client.get("/reelstudio/api/project")
    assert resp.status == 200
    data = await resp.json()
    assert abs(data["total_s"] - round(66 / 24, 4)) < 0.3
    assert [s["id"] for s in data["scenes"]] == ["s1_ramen", "s2_bowldrop", "s3_pinkburst"]
    assert all(s["stale"] and s["video_url"] is None for s in data["scenes"])
    assert data["scenes"][0]["first"]["kind"] == "still"
    assert data["scenes"][1]["first"]["kind"] == "prev_last"


async def test_render_stale_chain_end_to_end(client, workspace):
    resp = await client.post("/reelstudio/api/render", json={"stale": True})
    assert resp.status == 200
    jobs = (await resp.json())["jobs"]
    assert [j["target"] for j in jobs] == ["s1_ramen", "s2_bowldrop", "s3_pinkburst"]

    jobs = await wait_for_jobs(client)
    assert all(j["status"] == "done" for j in jobs), jobs

    # reel.py produced one deliverable per scene, in the reel dir
    reel_dir = workspace / "output" / "reel"
    for sid in ("s1_ramen", "s2_bowldrop", "s3_pinkburst"):
        assert list(reel_dir.glob(f"{sid}_*.mp4")), f"{sid} has no deliverable"

    # project view now shows fresh scenes with playable video urls
    resp = await client.get("/reelstudio/api/project")
    data = await resp.json()
    assert all(not s["stale"] for s in data["scenes"])
    assert all(s["video_url"] for s in data["scenes"])

    # the manifest vouches for the prev_last junction in the new format:
    # s2's recorded generation carries the resolved anchor, hashing s1's
    # current deliverable — an s1 re-render invalidates s2
    manifest = json.loads((reel_dir / ".reelstudio_manifest.json").read_text())
    first = manifest["scenes"]["s2_bowldrop"]["generation"]["first"]
    assert first["kind"] == "prev_last" and first["file_hash"]


async def test_yaml_edit_marks_exactly_the_affected_chain(client):
    await client.post("/reelstudio/api/render", json={"stale": True})
    jobs = await wait_for_jobs(client)
    assert all(j["status"] == "done" for j in jobs)

    # edit s2: only s2 is stale — s3 anchors on stills, not on s2
    resp = await client.get("/reelstudio/api/yaml")
    text = (await resp.json())["text"].replace(
        "The fox drops the bowl.", "The fox throws the bowl farther.")
    resp = await client.put("/reelstudio/api/yaml", json={"text": text})
    assert resp.status == 200

    data = await (await client.get("/reelstudio/api/project")).json()
    stale = {s["id"] for s in data["scenes"] if s["stale"]}
    assert stale == {"s2_bowldrop"}

    # edit s1: prev_last cascade pulls s2 in, still leaves s3 alone
    resp = await client.get("/reelstudio/api/yaml")
    text = (await resp.json())["text"].replace(
        "The fox eats noodles.", "The fox slurps the noodles.")
    resp = await client.put("/reelstudio/api/yaml", json={"text": text})
    assert resp.status == 200

    data = await (await client.get("/reelstudio/api/project")).json()
    stale = {s["id"] for s in data["scenes"] if s["stale"]}
    assert stale == {"s1_ramen", "s2_bowldrop"}


async def test_invalid_yaml_rejected_with_problems(client):
    resp = await client.get("/reelstudio/api/yaml")
    text = (await resp.json())["text"].replace(
        "next: s2_bowldrop", "next: wrong_id")
    resp = await client.put("/reelstudio/api/yaml", json={"text": text})
    assert resp.status == 400
    body = await resp.json()
    assert any("chain break" in p for p in body["problems"])


async def test_assemble_runs_the_pipeline_and_yields_the_final(client, workspace):
    await client.post("/reelstudio/api/render", json={"stale": True})
    jobs = await wait_for_jobs(client)
    assert all(j["status"] == "done" for j in jobs), jobs

    resp = await client.post("/reelstudio/api/assemble", json={"use_music": False})
    jobs = await wait_for_jobs(client)
    assert all(j["status"] == "done" for j in jobs), jobs

    data = await (await client.get("/reelstudio/api/project")).json()
    assert data["final_url"] is not None
    final = workspace / "output" / "final.mp4"
    assert final.exists()
    probe = json.loads(subprocess.run(
        ["/usr/bin/ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "json", str(final)], capture_output=True, check=True).stdout)
    assert float(probe["format"]["duration"]) > 0


async def test_render_unknown_scene_400_teaches(client):
    """Validation is uniform across generators: 400 + problems that name the
    valid targets, so the agent can self-correct without re-reading files."""
    resp = await client.post("/reelstudio/api/render", json={"scene_ids": ["nope"]})
    assert resp.status == 400
    body = await resp.json()
    assert any("s1_ramen" in p for p in body["problems"])


async def test_missing_reel_py_fails_the_job_loudly(client, workspace):
    """Without the pipeline script the job errors with a message that says so —
    never a silent pass or an unexplained crash."""
    (workspace / "reel.py").unlink()
    resp = await client.post("/reelstudio/api/render",
                             json={"scene_ids": ["s1_ramen"]})
    jobs = await wait_for_jobs(client)
    assert all(j["status"] == "error" for j in jobs)
    assert any("reel.py not found" in (j["error"] or "") for j in jobs)


async def test_music_segment_timing(client):
    from reelstudio.audio import music_segments
    from reelstudio.project import load

    from reelstudio.app import STATE_KEY

    project = load(client.app[STATE_KEY].config)
    assert music_segments(project) == []  # fixture reel has no anchored music

    # anchor one segment at s1: it runs to reel end
    project.raw["scenes"][0]["music"] = {"name": "opening", "caption": "rock"}
    segs = music_segments(project)
    assert len(segs) == 1
    assert segs[0]["name"] == "opening"
    assert segs[0]["start"] == 0.0
    assert abs(segs[0]["dur"] - round(66 / 24, 4)) < 0.01
    assert segs[0]["hash"]
