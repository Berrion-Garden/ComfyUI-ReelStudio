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


async def test_new_scene(client, workspace):
    save = await client.post("/reelstudio/api/studio/save",
                             json={"slug": "ep1"})
    assert save.status == 200

    resp = await client.post("/reelstudio/api/studio/scenes", json={
        "slug": "ep2", "title": "Episode 2"})
    assert resp.status == 200
    v = await resp.json()
    assert v["current"] == "ep2"

    scene = workspace / "scenes" / "ep2"
    assert (scene / "reel.yaml").is_file()
    assert (scene / "assets.yaml").exists()

    # the scaffolded scene is a valid project the app can load
    proj = await client.get("/reelstudio/api/project")
    assert proj.status == 200
    scenes = (await proj.json())["scenes"]
    assert [s["id"] for s in scenes] == ["s1_open"]


async def test_save_as_a_scene_dir_does_not_re_migrate(client, workspace):
    """Regression 2026-10-18: with the workspace configured as a scene dir
    whose registry lives at an ancestor, Save re-ran the migration and moved
    the whole scene into scenes/<slug>/scenes/<slug>/. The registry is
    updated in place instead."""
    await client.post("/reelstudio/api/studio/save", json={"slug": "ep1"})
    scene_dir = workspace / "scenes" / "ep1"
    assert (scene_dir / "reel.yaml").is_file()

    from reelstudio import studio
    out = studio.save_as(scene_dir, "ep1", "Episode One")
    assert out == scene_dir
    assert not (scene_dir / "scenes").exists()      # no nested migration
    assert (scene_dir / "reel.yaml").is_file()      # nothing moved
    reg = yaml.safe_load((workspace / "studio.yaml").read_text())
    assert reg["scenes"]["ep1"]["title"] == "Episode One"


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


async def test_agent_sees_studio(client):
    from reelstudio.app import STATE_KEY
    from reelstudio.agent.tools import ToolBox

    state = client.app[STATE_KEY]
    box = ToolBox(state)
    out = json.loads(await box.call("get_studio", {}))
    assert out["current"] == state.config.workspace.name


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


async def test_startup_resolves_a_root_configured_workspace(client, workspace):
    """config.json pointing at the studio ROOT: the app starts on the
    wrapper's current scene, not the root (which has no reel.yaml)."""
    from conftest import make_config
    from reelstudio import studio
    from reelstudio.app import STATE_KEY

    await client.post("/reelstudio/api/studio/save", json={"slug": "ep1"})
    await client.post("/reelstudio/api/studio/scenes", json={"slug": "ep2"})

    # a fresh app, configured the way config.json looks after a restart
    from reelstudio.app import create_app
    app2 = create_app(make_config(workspace))
    state2 = app2[STATE_KEY]
    assert state2.config.workspace == workspace / "scenes" / "ep2"
    assert state2.config.yaml_path == workspace / "scenes" / "ep2" / "reel.yaml"


async def test_upload_lands_in_library_dirs(client, workspace):
    import aiohttp

    def form(name, data, ctype):
        f = aiohttp.FormData()
        f.add_field("file", data, filename=name, content_type=ctype)
        return f

    ok = await client.post("/reelstudio/api/upload?dir=characters/unsorted",
                           data=form("ref-one.PNG", b"pngbytes", "image/png"))
    assert ok.status == 200
    body = await ok.json()
    assert body["path"] == "characters/unsorted/ref-one.png"
    assert (workspace / "characters/unsorted/ref-one.png").read_bytes() == b"pngbytes"

    # dedupe on collision
    dup = await client.post("/reelstudio/api/upload?dir=characters/unsorted",
                            data=form("ref-one.png", b"y", "image/png"))
    assert (await dup.json())["file"] == "ref-one-1.png"

    # the derived library picks it up with the pool label
    lib = await (await client.get("/reelstudio/api/assets")).json()
    sit = next(a for a in lib["groups"]["characters"]
               if a["path"].endswith("ref-one.png"))
    assert "char:unsorted" in sit["labels"]


async def test_upload_rejections(client, workspace):
    import aiohttp

    def form(name, data, ctype):
        f = aiohttp.FormData()
        f.add_field("file", data, filename=name, content_type=ctype)
        return f

    # an image extension does not belong in an audio dir, and vice versa
    bad_ext = await client.post("/reelstudio/api/upload?dir=audio",
                                data=form("tune.png", b"x", "image/png"))
    assert bad_ext.status == 400
    bad_dir = await client.post("/reelstudio/api/upload?dir=characters",
                                data=form("v.mp3", b"x", "audio/mpeg"))
    assert bad_dir.status == 400
    # unknown root and traversal are refused outright
    unknown = await client.post("/reelstudio/api/upload?dir=stills",
                                data=form("a.png", b"x", "image/png"))
    assert unknown.status == 400
    escape = await client.post("/reelstudio/api/upload?dir=../elsewhere",
                               data=form("a.png", b"x", "image/png"))
    assert escape.status == 403
    assert not list(workspace.glob("elsewhere")) and \
        not (workspace / "stills" / "a.png").exists()
