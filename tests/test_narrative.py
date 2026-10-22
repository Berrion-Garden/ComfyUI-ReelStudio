"""The production narrative: load/validate/normalize/save + the routes."""

import yaml


NARRATIVE = """
style: Cinematic anime, Jujutsu Kaisen action in a Mushi-shi atmosphere.
acts:
  - title: Act 1 — Waking Up
    music: Synched to the opening guitar riff and buildup.
    checkpoints:
      - title: Scene 1 — The Antique Shop
        characters: [Amun]
        locations: [antique_shop_dawn]
        shots:
          - title: "1.1 Establishing Shot"
            text: A dimly lit antique store interior at dawn.
      - title: Scene 2 — The Commute
        shots:
          - title: "2.1 The Walk"
            text: Walking alone across the bridge toward Nocturne High.
"""


async def test_default_when_absent(client, workspace):
    resp = await client.get("/reelstudio/api/narrative")
    assert resp.status == 200
    v = await resp.json()
    assert v["doc"]["acts"] == []  # a production starts before the file exists
    assert v["path"].endswith("storyboard.yaml")


async def test_put_get_roundtrip_normalized(client, workspace):
    resp = await client.put("/reelstudio/api/narrative", json={"doc": yaml.safe_load(NARRATIVE)})
    assert resp.status == 200
    saved = yaml.safe_load((workspace / "storyboard.yaml").read_text())
    cp = saved["acts"][0]["checkpoints"][0]
    assert cp["characters"] == ["Amun"]
    assert cp["locations"] == ["antique_shop_dawn"]
    assert cp["shots"][0]["text"].startswith("A dimly lit")

    # the display shape is total: every field present, everywhere
    v = await (await client.get("/reelstudio/api/narrative")).json()
    doc = v["doc"]
    assert doc["style"].startswith("Cinematic anime")
    act = doc["acts"][0]
    assert act["music"].startswith("Synched to")
    bare = act["checkpoints"][1]
    assert bare["characters"] == [] and bare["locations"] == []
    assert len(bare["shots"]) == 1


async def test_rejected_update_keeps_old(client, workspace):
    (workspace / "storyboard.yaml").write_text(NARRATIVE)
    for doc, problem in (
            ({"style": "no acts here"}, "'acts' must be a list"),
            ({"acts": [{"title": "Act", "checkpoints": [{"title": "S"}]}]},
             "'shots' must be a non-empty list"),
            ({"acts": [{"title": "Act", "checkpoints": [
                {"title": "S", "shots": [{"title": "1.1", "text": "x"}],
                 "characters": "Amun"}]}]},
             "'characters' must be a list"),
    ):
        resp = await client.put("/reelstudio/api/narrative", json={"doc": doc})
        assert resp.status == 400
        body = await resp.json()
        assert any(problem in p for p in body.get("problems", [body["error"]]))
    assert (workspace / "storyboard.yaml").read_text() == NARRATIVE


async def test_agent_text_path_parses_to_the_one_format(config):
    """The agent edits raw YAML text; storage stays the single doc format."""
    import json

    from reelstudio.agent.tools import ToolBox
    from reelstudio.app import ReelStudio

    state = ReelStudio(config)
    box = ToolBox(state)
    empty = json.loads(await box.call("get_narrative", {}))
    assert empty["doc"]["acts"] == []
    result = json.loads(await box.call("update_narrative", {"text": NARRATIVE}))
    assert result["saved"] is True
    saved = json.loads(await box.call("get_narrative", {}))
    cp = saved["doc"]["acts"][0]["checkpoints"][0]
    assert cp["characters"] == ["Amun"] and cp["shots"][0]["title"] == "1.1 Establishing Shot"
    rejected = json.loads(await box.call("update_narrative",
                                         {"text": "style: no acts here"}))
    assert rejected["error"]
