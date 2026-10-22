"""The production narrative: load/validate/save + the GET/PUT routes."""

import yaml


NARRATIVE = """
style: Cinematic anime, Jujutsu Kaisen action in a Mushi-shi atmosphere.
acts:
  - title: Act 1 — Waking Up
    music: Synched to the opening guitar riff and buildup.
    checkpoints:
      - title: Scene 1 — The Antique Shop
        text: |
          Prompt 1.1 (Establishing Shot): A dimly lit antique store at dawn.
        characters: [amunrekh]
        locations: [antique_shop]
      - title: Scene 2 — The Commute
        text: Walking alone across the bridge toward Nocturne High.
        characters: [amunrekh]
"""


async def test_default_when_absent(client, workspace):
    resp = await client.get("/reelstudio/api/narrative")
    assert resp.status == 200
    v = await resp.json()
    assert v["doc"]["acts"] == []  # a production starts before the file exists
    assert v["path"].endswith("storyboard.yaml")


async def test_put_get_roundtrip(client, workspace):
    resp = await client.put("/reelstudio/api/narrative", json={"text": NARRATIVE})
    assert resp.status == 200
    saved = yaml.safe_load((workspace / "storyboard.yaml").read_text())
    assert saved["acts"][0]["title"].startswith("Act 1")
    cp = saved["acts"][0]["checkpoints"][0]
    assert cp["characters"] == ["amunrekh"]
    assert cp["locations"] == ["antique_shop"]

    v = await (await client.get("/reelstudio/api/narrative")).json()
    assert v["doc"]["style"].startswith("Cinematic anime")
    assert len(v["doc"]["acts"][0]["checkpoints"]) == 2


async def test_rejected_update_keeps_old(client, workspace):
    (workspace / "storyboard.yaml").write_text(NARRATIVE)
    for text, problem in (("style: no acts here", "'acts' must be a list"),
                          (yaml.safe_dump({"acts": [{"title": "Act"}]}),
                           "'checkpoints' must be a list"),
                          ("{acts: broken", "yaml error")):
        resp = await client.put("/reelstudio/api/narrative",
                                json={"text": text})
        assert resp.status == 400
        body = await resp.json()
        assert any(problem in p for p in body.get("problems", [body["error"]]))
    assert (workspace / "storyboard.yaml").read_text() == NARRATIVE
