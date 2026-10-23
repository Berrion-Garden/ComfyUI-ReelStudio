"""The Storyboard's digested views: the per-scene prompt/beat on the read
model, and the pen-edit write path (PUT /api/block)."""

import yaml

YAML_PATH = "reel.yaml"


def _with_beat(workspace, beat="1.1"):
    doc = yaml.safe_load((workspace / YAML_PATH).read_text())
    doc["scenes"][0]["beat"] = beat
    (workspace / YAML_PATH).write_text(
        yaml.safe_dump(doc, sort_keys=False, allow_unicode=True))


async def test_scene_view_carries_beat_and_composed_prompt(client, workspace):
    _with_beat(workspace)
    resp = await client.get("/reelstudio/api/project")
    view = (await resp.json())["scenes"][0]
    assert view["beat"] == "1.1"
    # the stub's collapse composes from the wired beat's own description
    assert view["prompt"] is not None
    assert "The fox eats noodles" in view["prompt"]


async def test_scene_without_beat_still_renders(client, workspace):
    resp = await client.get("/reelstudio/api/project")
    view = (await resp.json())["scenes"][0]
    assert view["beat"] is None
    # the prompt composes from the scene's own description — no beat needed
    assert view["prompt"] is not None


async def test_block_put_edits_one_location(client, workspace):
    block = (await (await client.get("/reelstudio/api/project")).json()
             )["location_blocks"]["campus_sunset"]
    block["pro"] = "university campus plaza at night, neon signs"
    resp = await client.put("/reelstudio/api/block", json={
        "section": "locations", "slug": "campus_sunset", "block": block})
    assert resp.status == 200

    blocks = (await (await client.get("/reelstudio/api/project")).json()
              )["location_blocks"]
    assert blocks["campus_sunset"]["pro"].endswith("neon signs")


async def test_block_put_rejects_unknown_section_and_slug(client, workspace):
    for body, status in (
            ({"section": "stills", "slug": "x", "block": {}}, 400),
            ({"section": "locations", "slug": "no_such", "block": {}}, 404),
            ({"section": "locations", "slug": "campus_sunset",
              "block": "not a dict"}, 400),
    ):
        resp = await client.put("/reelstudio/api/block", json=body)
        assert resp.status == status


async def test_block_put_validation_covers_the_block(client, workspace):
    # the block must carry a mapping shape; the server validates the dump
    resp = await client.put("/reelstudio/api/block", json={
        "section": "locations", "slug": "campus_sunset",
        "block": {"pro": "dusk", "con": None}})
    assert resp.status == 200
