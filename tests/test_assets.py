"""Asset library: group/label derivation, sandboxed serving, music URLs."""

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


async def test_project_exposes_music_urls(client, workspace, fake_comfy):
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
