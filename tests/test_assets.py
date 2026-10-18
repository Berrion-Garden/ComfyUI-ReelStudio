"""Asset library: group/label derivation, sandboxed serving, music URLs."""

import json

import yaml
from pathlib import Path


async def test_index_derives_groups_and_labels(config, workspace):
    from reelstudio import assets as assets_mod
    from reelstudio.project import load

    ws = workspace
    (ws / "characters" / "fox_boy").mkdir(parents=True)
    (ws / "characters" / "fox_boy" / "sit_.png").write_bytes(b"x")
    (ws / "characters" / "fox_boy" / "run_.png").write_bytes(b"x")
    (ws / "images").mkdir()
    (ws / "images" / "moodboard.png").write_bytes(b"x")
    (ws / "themes").mkdir()
    (ws / "themes" / "night.yaml").write_text(
        "slug: night\nlora: night_syle_v2\nlabels: [dark]\n")
    (ws / "audio").mkdir()
    (ws / "audio" / "sfx_pop.mp3").write_bytes(b"x")
    (ws / "assets.yaml").write_text(
        "labels:\n  characters/fox_boy/run_.png: [hero, main-walk]\n")

    project = load(config)
    data = assets_mod.index_assets(ws, project)
    g = data["groups"]

    by_slug = {a["slug"]: a for a in g["scenes"]}
    assert by_slug["opening_still"]["labels"] == ["still", "still:opening"]
    assert by_slug["opening_still"]["used_by"] == ["s1_ramen"]
    assert by_slug["impact_still"]["used_by"] == ["s3_pinkburst"]

    poses = {a["slug"]: a for a in g["characters"]}
    assert set(poses) == {"sit", "run"}
    assert poses["sit"]["labels"] == ["char:fox_boy", "pose:sit"]
    # declared labels cross-group onto the derived ones, order-stable
    assert poses["run"]["labels"] == ["char:fox_boy", "pose:run", "hero", "main-walk"]

    assert [a["slug"] for a in g["custom"]] == ["moodboard"]
    theme = g["themes"][0]
    assert theme["labels"] == ["theme:night", "dark"]
    assert [a["slug"] for a in g["audio"]] == ["sfx_pop"]


async def test_asset_file_serves_within_roots_only(client, workspace):
    inside = workspace / "images" / "ok.png"
    inside.parent.mkdir(exist_ok=True)
    inside.write_bytes(b"pngbytes")

    ok = await client.get(
        "/reelstudio/api/asset/file",
        params={"path": str(inside)})
    assert ok.status == 200
    assert b"pngbytes" in await ok.read()

    escape = await client.get(
        "/reelstudio/api/asset/file",
        params={"path": str(workspace / ".." / ".." / "etc" / "passwd")})
    assert escape.status == 403

    missing = await client.get(
        "/reelstudio/api/asset/file",
        params={"path": str(workspace / "images" / "nope.png")})
    assert missing.status == 404

    # a directory inside the roots is not an asset
    directory = await client.get(
        "/reelstudio/api/asset/file",
        params={"path": str(workspace / "images")})
    assert directory.status == 404


async def test_project_exposes_music_urls(client, workspace):
    import yaml as yaml_mod

    from reelstudio.project import load

    project = load(config_of(workspace))
    reel_dir = Path(project.meta["reel_dir"])
    reel_dir.mkdir(parents=True, exist_ok=True)
    # a render that predates the manifest entirely (no record_music call):
    # the file on disk is still the deliverable
    (reel_dir / "music_opening_00001_.wav").write_bytes(b"wav")
    (reel_dir / "music_opening_00001_.json").write_text("{}")  # never served

    # anchor a music segment on s1 so the project view advertises it
    text = (workspace / "reel.yaml").read_text()
    (workspace / "reel.yaml").write_text(text.replace(
        "      soundscape: slurp\n",
        "      soundscape: slurp\n    music:\n      name: opening\n      caption: rock\n",
        1))
    assert yaml_mod.safe_load((workspace / "reel.yaml").read_text())

    data = await (await client.get("/reelstudio/api/project")).json()
    opening = next(m for m in data["music"] if m["name"] == "opening")
    assert opening["present"] is True
    assert opening["stale"] is True  # no manifest entry to vouch for it
    assert opening["url"].endswith("/api/music/opening/artifact")

    audio = await client.get(opening["url"])
    assert audio.status == 200
    assert b"wav" in await audio.read()
    missing = await client.get("/reelstudio/api/music/battle/artifact")
    assert missing.status == 404


def config_of(ws):
    from tests.conftest import make_config

    return make_config(ws)


async def test_overlays_come_from_audio_array(client, workspace, tmp_path):
    """The timeline's real audio tracks: top-level `audio:` entries with their
    actual span (absolute `at` → last fades keyframe), served from wherever
    reel.yaml points — including outside the workspace."""
    track = tmp_path / "music" / "01 - Test Artist - Night Run.mp3"
    track.parent.mkdir()
    track.write_bytes(b"mp3bytes")

    text = (workspace / "reel.yaml").read_text()
    (workspace / "reel.yaml").write_text(text + (
        "\naudio:\n"
        f"  - file: \"{track}\"\n"
        "    at: 0.1\n"
        "    seek: 71.0\n"
        "    gain: 1.0\n"
        "    fades: [[0.5, 1.0], [2.0, 0.0]]\n"))

    data = await (await client.get("/reelstudio/api/project")).json()
    assert len(data["overlays"]) == 1
    ov = data["overlays"][0]
    assert ov["name"] == "01 - Test Artist - Night Run"  # derived from the file
    assert ov["start_s"] == 0.1
    assert ov["duration_s"] == 1.9  # last fades keyframe
    assert ov["fades"] == [[0.5, 1.0], [2.0, 0.0]]
    assert ov["present"] is True
    assert ov["url"].endswith("/api/audio/0/artifact")

    served = await client.get(ov["url"])
    assert served.status == 200
    assert b"mp3bytes" in await served.read()

    missing_index = await client.get("/reelstudio/api/audio/7/artifact")
    assert missing_index.status == 404


async def test_overlay_without_fades_runs_to_reel_end(client, workspace, tmp_path):
    track = tmp_path / "music" / "loop.mp3"
    track.parent.mkdir()
    track.write_bytes(b"x")
    text = (workspace / "reel.yaml").read_text()
    (workspace / "reel.yaml").write_text(text + (
        "\naudio:\n"
        f"  - file: \"{track}\"\n"))

    data = await (await client.get("/reelstudio/api/project")).json()
    ov = data["overlays"][0]
    assert ov["start_s"] == 0
    assert ov["duration_s"] == data["total_s"]
    assert ov["seek"] == 0.0


async def test_sfx_assets_get_their_own_group_and_label(config, workspace):
    from reelstudio import assets as assets_mod
    from reelstudio.project import load

    ws = workspace
    (ws / "sfx").mkdir()
    (ws / "sfx" / "school_bell.wav").write_bytes(b"x")

    data = assets_mod.index_assets(ws, load(config))
    bell = next(a for a in data["groups"]["sfx"] if a["slug"] == "school_bell")
    assert bell["labels"] == ["sfx", "sfx:school_bell"]
    assert "sfx" not in {a["slug"]: a for a in data["groups"]["audio"]}


async def test_backgrounds_are_their_own_group(config, workspace):
    from reelstudio import assets as assets_mod
    from reelstudio.project import load

    (workspace / "backgrounds").mkdir()
    (workspace / "backgrounds" / "campus_sunset.png").write_bytes(b"x")
    data = assets_mod.index_assets(workspace, load(config))
    bg = data["groups"]["backgrounds"]
    assert [a["slug"] for a in bg] == ["campus_sunset"]
    assert bg[0]["labels"] == ["background"]


async def test_put_labels_round_trips_through_assets_yaml(client, workspace):
    (workspace / "images").mkdir()
    (workspace / "images" / "tony_face_.png").write_bytes(b"x")
    (workspace / "assets.yaml").write_text(
        "# declared labels — the one owner\nlabels: {}\n")

    resp = await client.put("/reelstudio/api/assets/labels", json={
        "path": str(workspace / "images" / "tony_face_.png"),
        "labels": ["char:tony", "scene:s1_ramen", "cond:human"]})
    assert resp.status == 200

    # the yaml keeps its comment and gains the typed labels
    text = (workspace / "assets.yaml").read_text()
    assert "# declared labels" in text
    assert "char:tony" in text

    # the index merges the declared labels in
    data = await (await client.get("/reelstudio/api/assets")).json()
    items = [a for g in data["groups"].values() for a in g
             if a["slug"].startswith("tony_face")]
    assert items, "asset indexed"
    assert {"char:tony", "scene:s1_ramen", "cond:human"} <= set(items[0]["labels"])

    # clearing the list removes the entry (no [] residue)
    resp = await client.put("/reelstudio/api/assets/labels", json={
        "path": str(workspace / "images" / "tony_face_.png"), "labels": []})
    assert resp.status == 200
    assert "char:tony" not in (workspace / "assets.yaml").read_text()


async def test_put_labels_rejects_paths_outside_the_roots(client):
    bad = await client.put("/reelstudio/api/assets/labels", json={
        "path": "/etc/passwd", "labels": ["nope"]})
    assert bad.status == 403


async def test_agent_currently_selected_tool(config, workspace):
    from reelstudio.agent.tools import ToolBox
    from reelstudio.app import ReelStudio

    (workspace / "characters" / "tony").mkdir(parents=True)
    (workspace / "characters" / "tony" / "face_.png").write_bytes(b"x")
    state = ReelStudio(config)

    # the tool answers from the request-scoped selection the FE sends,
    # with labels refreshed from the index (the FE copy can be stale)
    box = ToolBox(state, selected={
        "path": str(workspace / "characters" / "tony" / "face_.png"),
        "slug": "face", "group": "characters"})
    out = json.loads(await box.call("currently_selected", {}))
    assert out["selected"]["slug"] == "face"
    assert out["selected"]["labels"] == ["char:tony", "pose:face"]

    assert json.loads(await ToolBox(state).call("currently_selected", {}))[
        "selected"] is None


async def test_unanchored_stills_are_candidates(config, workspace):
    from reelstudio import assets as assets_mod
    from reelstudio.project import load

    # the fixture's stills map anchors opening_still; a stray generation in
    # the still dir is a candidate until the operator anchors it by name
    stray = workspace / "stills" / "tony_dunk01_00001_.png"
    stray.write_bytes(b"x")
    data = assets_mod.index_assets(workspace, load(config))
    slugs = [a["slug"] for a in data["groups"]["stills"]]
    assert "tony_dunk01_00001" in slugs
    assert "opening_still" not in slugs  # anchored stills stay in scenes


async def test_delete_only_non_verified(client, workspace):
    import hashlib
    (workspace / "images").mkdir()
    (workspace / "images" / "gen_a_.png").write_bytes(b"x")
    (workspace / "images" / "keep_.png").write_bytes(b"x")
    for name, labels in [("images/gen_a_.png", ["char:tony", "non-verified"]),
                         ("images/keep_.png", ["char:tony"])]:
        r = await client.put("/reelstudio/api/assets/labels", json={
            "path": str(workspace / name), "labels": labels})
        assert r.status == 200

    # a verified asset is not deletable
    bad = await client.delete("/reelstudio/api/asset", json={
        "path": str(workspace / "images" / "keep_.png")})
    assert bad.status == 403
    assert (workspace / "images" / "keep_.png").exists()

    # a non-verified asset deletes the file and drops its label entry
    ok = await client.delete("/reelstudio/api/asset", json={
        "path": str(workspace / "images" / "gen_a_.png")})
    assert ok.status == 200
    assert not (workspace / "images" / "gen_a_.png").exists()
    assert "gen_a_" not in (workspace / "assets.yaml").read_text()
