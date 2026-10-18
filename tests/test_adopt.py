"""Manifest adoption: pre-app renders become the staleness baseline."""


async def test_adopt_records_existing_deliverables(config, workspace):
    from pathlib import Path

    from reelstudio import manifest as manifest_mod
    from reelstudio.project import load
    from reelstudio.timeline import stale_scenes

    project = load(config)
    reel_dir = project.meta["reel_dir"]
    Path(reel_dir).mkdir(parents=True, exist_ok=True)
    for s in project.scenes:
        (Path(reel_dir) / f"{s['id']}_00001_.mp4").write_bytes(b"x")

    # no manifest: everything stale
    assert len(stale_scenes(project, {}, reel_dir)) == 3

    adopted = manifest_mod.adopt_existing(reel_dir, project)
    assert adopted == 3
    data = manifest_mod.load(reel_dir)
    assert all(data["scenes"][s["id"]]["adopted"] for s in project.scenes)
    assert stale_scenes(project, manifest_mod.load(reel_dir), reel_dir) == []

    # adopting is idempotent and never overwrites a real render entry
    assert manifest_mod.adopt_existing(reel_dir, project) == 0


async def test_adopt_marks_prev_last_junctions(config, workspace):
    from pathlib import Path

    from reelstudio import manifest as manifest_mod
    from reelstudio.project import load
    from reelstudio.timeline import stale_scenes

    project = load(config)
    reel_dir = project.meta["reel_dir"]
    Path(reel_dir).mkdir(parents=True, exist_ok=True)
    for s in project.scenes:
        (Path(reel_dir) / f"{s['id']}_00001_.mp4").write_bytes(b"x")
    manifest_mod.adopt_existing(reel_dir, project)
    data = manifest_mod.load(reel_dir)
    assert data["scenes"]["s2_bowldrop"]["upstream"]["file"] == "s1_ramen_00001_.mp4"

    # an upstream re-render AFTER adoption re-stales the junction — adopted
    # renders participate in staleness like any other
    import json as json_mod

    entry = data["scenes"]["s1_ramen"]
    entry["video"]["path"]["file"] = "s1_ramen_00002_.mp4"
    (Path(reel_dir) / "s1_ramen_00002_.mp4").write_bytes(b"x")
    (Path(reel_dir) / ".reelstudio_manifest.json").write_text(json_mod.dumps(data))
    assert stale_scenes(project, manifest_mod.load(reel_dir), reel_dir) == \
        ["s2_bowldrop"]


async def test_adopt_endpoint(client, workspace):
    await client.post("/reelstudio/api/manifest/adopt")
    data = await (await client.get("/reelstudio/api/project")).json()
    # fixture workspace has no renders yet: nothing to adopt, still stale
    assert all(s["stale"] for s in data["scenes"])
