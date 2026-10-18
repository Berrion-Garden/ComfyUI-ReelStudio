"""The studio wrapper: save-as migration, scene creation, switching, import."""

import json

import yaml

from conftest import wait_for_jobs


async def get_studio(client):
    resp = await client.get("/reelstudio/api/studio")
    assert resp.status == 200
    return await resp.json()


async def test_implicit_then_save_as(client, workspace):
    v = await get_studio(client)
    assert v["saved"] is False
    assert v["current"] == workspace.name
    assert [s["slug"] for s in v["scenes"]] == [workspace.name]

    resp = await client.post("/reelstudio/api/studio/save",
                             json={"slug": "court", "title": "The Court"})
    assert resp.status == 200
    v = await resp.json()
    assert v["saved"] is True
    assert v["current"] == "court"
    assert v["workspace"].endswith("scenes/court")

    # the project moved; the app was rebound and still serves it
    assert (workspace / "scenes" / "court" / "reel.yaml").is_file()
    assert (workspace / "reel.py").is_file()  # the pipeline stays at the root
    proj = await client.get("/reelstudio/api/project")
    assert proj.status == 200
    v = await get_studio(client)
    assert v["current"] == "court" and v["saved"] is True


async def test_new_scene_with_import(client, workspace):
    (workspace / "characters" / "fox_boy").mkdir(parents=True)
    (workspace / "characters" / "fox_boy" / "sit_.png").write_bytes(b"x")
    (workspace / "backgrounds").mkdir()
    (workspace / "backgrounds" / "campus.png").write_bytes(b"y")
    (workspace / "assets.yaml").write_text(
        "labels:\n"
        "  characters/fox_boy/sit_.png: [char:fox_boy, scene:s1_ramen]\n"
        "  backgrounds/campus.png: [background, scene:s1_ramen]\n")

    save = await client.post("/reelstudio/api/studio/save",
                             json={"slug": "ep1"})
    assert save.status == 200

    resp = await client.post("/reelstudio/api/studio/scenes", json={
        "slug": "ep2", "title": "Episode 2",
        "import": {"from": "ep1", "characters": ["fox_boy"],
                   "backgrounds": ["campus.png"]}})
    assert resp.status == 200
    v = await resp.json()
    assert v["current"] == "ep2"
    assert v["import"]["imported"] == [
        "backgrounds/campus.png", "characters/fox_boy/sit_.png"]

    scene = workspace / "scenes" / "ep2"
    assert (scene / "characters" / "fox_boy" / "sit_.png").is_file()
    assert (scene / "backgrounds" / "campus.png").is_file()
    labels = yaml.safe_load((scene / "assets.yaml").read_text())["labels"]
    assert labels["characters/fox_boy/sit_.png"] == ["char:fox_boy"]
    assert labels["backgrounds/campus.png"] == ["background"]

    # the scaffolded scene is a valid project the app can load
    proj = await client.get("/reelstudio/api/project")
    assert proj.status == 200
    scenes = (await proj.json())["scenes"]
    assert [s["id"] for s in scenes] == ["s1_open"]


async def test_open_scene_switches_and_rebinds(client, workspace):
    await client.post("/reelstudio/api/studio/save", json={"slug": "ep1"})
    await client.post("/reelstudio/api/studio/scenes", json={"slug": "ep2"})

    resp = await client.post("/reelstudio/api/studio/open",
                             json={"slug": "ep1"})
    assert resp.status == 200
    v = await resp.json()
    assert v["current"] == "ep1"
    assert v["workspace"].endswith("scenes/ep1")
    proj = await client.get("/reelstudio/api/project")
    assert proj.status == 200

    unknown = await client.post("/reelstudio/api/studio/open",
                                json={"slug": "nope"})
    assert unknown.status == 404


async def test_import_collision_refused(client, workspace):
    (workspace / "characters" / "fox_boy").mkdir(parents=True)
    (workspace / "characters" / "fox_boy" / "sit_.png").write_bytes(b"x")
    await client.post("/reelstudio/api/studio/save", json={"slug": "ep1"})
    await client.post("/reelstudio/api/studio/scenes", json={"slug": "ep2"})
    # import from ep1 into the current scene (ep2) works…
    ok = await client.post("/reelstudio/api/studio/import",
                           json={"from": "ep1", "characters": ["fox_boy"]})
    assert ok.status == 200
    # …and a second time collides with nothing partial left behind
    bad = await client.post("/reelstudio/api/studio/import",
                            json={"from": "ep1", "characters": ["fox_boy"]})
    assert bad.status == 400
    assert "already exists" in (await bad.read()).decode()


async def test_agent_sees_studio(client):
    from reelstudio.app import STATE_KEY
    from reelstudio.agent.tools import ToolBox

    state = client.app[STATE_KEY]
    box = ToolBox(state)
    out = json.loads(await box.call("get_studio", {}))
    assert out["current"] == state.config.workspace.name
    out = json.loads(await box.call("import_assets",
                                    {"from": "nowhere", "characters": []}))
    assert "error" in out


async def test_seam_finds_studio_root_reel_py(workspace):
    from reelstudio import studio
    from reelstudio.reel import workspace_script

    scene = studio.save_as(workspace, "court", "The Court")
    assert workspace_script(scene) == (workspace / "reel.py").resolve()


async def test_render_runs_from_a_migrated_scene(client):
    """After save-as the app runs the ONE shared reel.py with cwd = the
    scene dir — the full seam (walk-up script, scene cwd) end to end."""
    await client.post("/reelstudio/api/studio/save", json={"slug": "court"})
    resp = await client.post("/reelstudio/api/render", json={"stale": True})
    assert resp.status == 200
    jobs = await wait_for_jobs(client)
    assert all(j["status"] == "done" for j in jobs), [j["error"] for j in jobs]


async def test_per_scene_adopt_and_adoptable_flag(client, workspace):
    """An unmanaged render on disk: adoptable on the read model, ✓ adopts
    just that scene, and the manifest then vouches for it."""
    import shutil

    from reelstudio.app import STATE_KEY

    state = client.app[STATE_KEY]
    reel_dir = workspace / "output" / "reel"
    reel_dir.mkdir(parents=True)
    shutil.copy(workspace / "stills" / "opening_still_.png",
                reel_dir / "s1_ramen_0001.mp4")  # a deliverable nobody recorded

    view = await (await client.get("/reelstudio/api/project")).json()
    scene = next(s for s in view["scenes"] if s["id"] == "s1_ramen")
    assert scene["adoptable"] is True and scene["stale"] is True

    resp = await client.post("/reelstudio/api/manifest/adopt",
                             json={"scene_id": "s1_ramen"})
    assert resp.status == 200

    view = await (await client.get("/reelstudio/api/project")).json()
    scene = next(s for s in view["scenes"] if s["id"] == "s1_ramen")
    assert scene["adoptable"] is False
    assert scene["video_url"] is not None
    other = next(s for s in view["scenes"] if s["id"] != "s1_ramen")
    assert other["adoptable"] is False and other["video_url"] is None
