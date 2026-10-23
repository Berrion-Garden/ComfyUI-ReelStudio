"""The LLM reviews: one reviewer agent per kind (prompts, entities,
frames), their findings merged into the panel."""

import asyncio
import json
import subprocess
from pathlib import Path

import yaml

import pytest


async def _poll(client, kinds, deadline_s: float = 30.0) -> dict:
    """The reviews run as server tasks; the report files are the channel."""
    for _ in range(int(deadline_s * 5)):
        reports = (await (await client.get("/reelstudio/api/validate")).json()
                   )["reports"]
        if all(reports[k].get("state") in ("done", "error")
               for k in kinds if reports.get(k)):
            return reports
        await asyncio.sleep(0.2)
    raise AssertionError("validate run did not finish")


def _assemble(workspace):
    """A real (ffmpeg-rendered) final cut long enough for the segment
    midpoints the frame review extracts frames at."""
    doc = yaml.safe_load((workspace / "reel.yaml").read_text())
    final = Path(doc["meta"]["final"])
    final.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["/usr/bin/ffmpeg", "-y", "-v", "error",
                    "-f", "lavfi", "-i", "color=c=0x225588:s=64x64:r=8:d=30",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(final)],
                   check=True, capture_output=True)


NARRATIVE = """
style: cinematic anime
acts:
- title: Act 1
  music: guitar
  checkpoints:
  - title: Scene 1 — Ramen
    characters: [fox]
    locations: [campus_sunset]
    shots:
    - title: 1.1 Ramen
      text: The fox eats noodles under a warm sunset.
  - title: Scene 2 — Bowldrop
    locations: [campus_dawn]
    shots:
    - title: 2.1 Drop
      text: The bowl drops and bursts.
  - title: Scene 3 — Pink
    locations: [campus_sunset]
    shots:
    - title: 3.1 Burst
      text: A pink explosion fills the frame.
"""


def _wire(workspace):
    """A narrative doc + beats on the scenes — the two artifacts the text
    reviews read."""
    (workspace / "storyboard.yaml").write_text(NARRATIVE)
    doc = yaml.safe_load((workspace / "reel.yaml").read_text())
    for i, s in enumerate(doc["scenes"], 1):
        s["beat"] = f"{i}.1"
    (workspace / "reel.yaml").write_text(
        yaml.safe_dump(doc, sort_keys=False, allow_unicode=True))


def _fake_llm(monkeypatch, respond):
    """The reviewer never touches the real gateway; `respond` gets the
    row items it must answer for."""
    from reelstudio.agent import llm

    async def fake_chat(config, messages, tools):
        assert tools == []
        content = messages[0]["content"]
        text = content[0]["text"] if isinstance(content, list) else content
        return {"content": respond(text)}

    monkeypatch.setattr(llm, "chat", fake_chat)


async def test_prompts_review_reads_beat_text_vs_composed_prompt(
        client, workspace, monkeypatch):
    _wire(workspace)
    seen = {}

    def respond(text):
        seen["listing"] = text
        return json.dumps(
            [{"item": "s1_ramen", "verdict": "issue",
              "note": "beat text reworded"},
             {"item": "s2_bowldrop", "verdict": "ok", "note": "fair merge"},
             {"item": "s3_pinkburst", "verdict": "ok", "note": "fair merge"}])

    _fake_llm(monkeypatch, respond)
    resp = await client.post("/reelstudio/api/validate",
                             json={"kinds": ["prompts"]})
    assert resp.status == 200

    reports = await _poll(client, ["prompts"])
    report = reports["prompts"]
    assert report["state"] == "done", report
    assert report["total"] == 3
    # the listing carried BOTH texts the reviewer must compare
    assert "original:" in seen["listing"] and "final:" in seen["listing"]
    issue = next(f for f in report["findings"] if f["verdict"] == "issue")
    assert issue["item"] == "s1_ramen"


async def test_entities_review_reads_blocks_vs_narrative_excerpts(
        client, workspace, monkeypatch):
    _wire(workspace)
    seen = {}

    def respond(text):
        seen["listing"] = text
        return json.dumps(
            [{"item": "campus_sunset", "verdict": "issue",
              "note": "narrative needs a night setting"},
             {"item": "campus_dawn", "verdict": "ok", "note": "consistent"}])

    _fake_llm(monkeypatch, respond)
    resp = await client.post("/reelstudio/api/validate",
                             json={"kinds": ["entities"]})
    assert resp.status == 200

    reports = await _poll(client, ["entities"])
    report = reports["entities"]
    assert report["state"] == "done", report
    # both location blocks were reviewed (the fixture has no characters)
    assert report["total"] == 2
    assert "directives:" in seen["listing"]
    assert "narrative:" in seen["listing"]


async def test_frames_review_reads_midpoint_frames(
        client, workspace, monkeypatch):
    _assemble(workspace)
    _fake_llm(monkeypatch, lambda text: json.dumps(
        [{"item": "s1_ramen", "verdict": "issue", "note": "wrong subject"},
         {"item": "s2_bowldrop", "verdict": "ok", "note": "fair midpoint"},
         {"item": "s3_pinkburst", "verdict": "ok", "note": "fair midpoint"}]))

    resp = await client.post("/reelstudio/api/validate",
                             json={"kinds": ["frames"]})
    assert resp.status == 200

    reports = await _poll(client, ["frames"])
    assert reports["frames"]["state"] == "done"
    issue = next(f for f in reports["frames"]["findings"]
                 if f["verdict"] == "issue")
    assert issue["item"] == "s1_ramen"


async def test_kinds_run_in_parallel_and_merge_back(
        client, workspace, monkeypatch):
    _wire(workspace)
    _assemble(workspace)
    _fake_llm(monkeypatch, lambda text: json.dumps(
        [{"item": "s1_ramen", "verdict": "issue", "note": "x"},
         {"item": "s2_bowldrop", "verdict": "ok", "note": ""},
         {"item": "s3_pinkburst", "verdict": "ok", "note": ""}]))

    resp = await client.post("/reelstudio/api/validate",
                             json={"kinds": ["prompts", "entities", "frames"]})
    assert resp.status == 200
    assert sorted((await resp.json())["started"]) == \
        ["entities", "frames", "prompts"]

    reports = await _poll(client, ["prompts", "entities", "frames"])
    # the merged view: every kind reported separately
    assert {k for k, r in reports.items() if r["state"] == "done"} == \
        {"prompts", "entities", "frames"}


async def test_a_running_kind_is_not_double_started(client, workspace,
                                                    monkeypatch):
    _assemble(workspace)
    from reelstudio.agent import llm
    release = asyncio.Event()

    async def slow_chat(config, messages, tools):
        await release.wait()
        return {"content": "[]"}

    monkeypatch.setattr(llm, "chat", slow_chat)
    await client.post("/reelstudio/api/validate", json={"kinds": ["frames"]})
    reports = (await (await client.get("/reelstudio/api/validate")).json()
               )["reports"]
    for _ in range(50):
        if reports.get("frames", {}).get("state") == "running":
            break
        reports = (await (await client.get(
            "/reelstudio/api/validate")).json())["reports"]
        await asyncio.sleep(0.1)
    assert reports["frames"]["state"] == "running"

    resp = await client.post("/reelstudio/api/validate",
                             json={"kinds": ["frames"]})
    assert resp.status == 200
    assert (await resp.json())["already_running"] == ["frames"]
    release.set()
    await _poll(client, ["frames"])


async def test_bad_kinds_are_rejected(client, workspace):
    resp = await client.post("/reelstudio/api/validate", json={"kinds": ["x"]})
    assert resp.status == 400
    resp = await client.post("/reelstudio/api/validate", json={"kinds": []})
    assert resp.status == 400


async def test_prompts_review_reports_a_broken_pipeline(client, workspace,
                                                        monkeypatch):
    from reelstudio import collapse as collapse_mod
    monkeypatch.setattr(collapse_mod, "current", lambda project: None)
    _fake_llm(monkeypatch, lambda text: "[]")
    resp = await client.post("/reelstudio/api/validate",
                             json={"kinds": ["prompts"]})
    assert resp.status == 200
    reports = await _poll(client, ["prompts"])
    assert reports["prompts"]["state"] == "error"
    assert "reel.py" in reports["prompts"]["error"]


@pytest.fixture(autouse=True)
def _hermetic_llm(monkeypatch):
    """The validate runs must never touch the real gateway."""
    from reelstudio.agent import llm
    monkeypatch.setattr(llm, "chat",
                        lambda *a, **k: (_ for _ in ()).throw(
                            AssertionError("gateway reached")))
