"""Manifest adoption: pre-app renders become the staleness baseline."""


async def test_adopt_records_existing_deliverables(config, workspace):
    from pathlib import Path

    from reelstudio import collapse as collapse_mod
    from reelstudio import manifest as manifest_mod
    from reelstudio.project import load
    from reelstudio.timeline import stale_scenes

    project = load(config)
    reel_dir = project.meta["reel_dir"]
    Path(reel_dir).mkdir(parents=True, exist_ok=True)
    for s in project.scenes:
        (Path(reel_dir) / f"{s['id']}_00001_.mp4").write_bytes(b"x")

    # no manifest: everything stale
    collapse = collapse_mod.current(project)
    assert len(stale_scenes(project, {}, reel_dir, collapse)) == 3

    adopted = manifest_mod.adopt_existing(reel_dir, project)
    assert adopted == 3
    data = manifest_mod.load(reel_dir)
    assert all(data["scenes"][s["id"]]["adopted"] for s in project.scenes)
    fresh = collapse_mod.current(project)
    assert stale_scenes(project, manifest_mod.load(reel_dir), reel_dir,
                        collapse=fresh) == []

    # adopting is idempotent — converted entries have generation, so adopt
    # leaves managed scenes alone
    assert manifest_mod.adopt_existing(reel_dir, project) == 0


async def test_adopt_converts_entries_and_cascades_upstream(config, workspace):
    from pathlib import Path

    from reelstudio import collapse as collapse_mod
    from reelstudio import manifest as manifest_mod
    from reelstudio.project import load
    from reelstudio.timeline import stale_scenes

    project = load(config)
    reel_dir = project.meta["reel_dir"]
    Path(reel_dir).mkdir(parents=True, exist_ok=True)
    for s in project.scenes:
        (Path(reel_dir) / f"{s['id']}_00001_.mp4").write_bytes(b"x")
    adopted = manifest_mod.adopt_existing(reel_dir, project)
    assert adopted == 3
    data = manifest_mod.load(reel_dir)
    assert all(data["scenes"][s["id"]]["adopted"] for s in project.scenes)
    assert all(data["scenes"][s["id"]]["generation"] for s in project.scenes)
    fresh = collapse_mod.current(project)
    assert stale_scenes(project, manifest_mod.load(reel_dir), reel_dir,
                        collapse=fresh) == []

    # an upstream re-render AFTER adoption re-stales the dependent — the
    # resolved prev_last anchor hashes the upstream's current deliverable
    import json as json_mod

    (Path(reel_dir) / "s1_ramen_00002_.mp4").write_bytes(b"y")
    data["scenes"]["s1_ramen"]["video"]["path"]["file"] = "s1_ramen_00002_.mp4"
    (Path(reel_dir) / ".reelstudio_manifest.json").write_text(json_mod.dumps(data))
    fresh = collapse_mod.current(project)
    assert stale_scenes(project, manifest_mod.load(reel_dir), reel_dir,
                        collapse=fresh) == ["s2_bowldrop"]


async def test_adopt_endpoint(client, workspace):
    await client.post("/reelstudio/api/manifest/adopt")
    data = await (await client.get("/reelstudio/api/project")).json()
    # fixture workspace has no renders yet: nothing to adopt, still stale
    assert all(s["stale"] for s in data["scenes"])
