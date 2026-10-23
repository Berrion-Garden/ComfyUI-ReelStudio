"""The LLM review: the narrative vs the final cut, as the chat tab reads it."""

import asyncio
import json
import subprocess
from pathlib import Path

import yaml

import pytest


async def _poll(client, deadline_s: float = 30.0) -> dict:
    """The review runs as a server task; the report file is the channel."""
    for _ in range(int(deadline_s * 5)):
        report = (await (await client.get("/reelstudio/api/validate")).json()
                  )["report"]
        if report.get("state") in ("done", "error"):
            return report
        await asyncio.sleep(0.2)
    raise AssertionError("validate run did not finish")


def _assemble(workspace):
    """A real (ffmpeg-rendered) final cut long enough for the segment
    midpoints the review extracts frames at."""
    doc = yaml.safe_load((workspace / "reel.yaml").read_text())
    final = Path(doc["meta"]["final"])
    final.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["/usr/bin/ffmpeg", "-y", "-v", "error",
                    "-f", "lavfi", "-i", "color=c=0x225588:s=64x64:r=8:d=30",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(final)],
                   check=True, capture_output=True)


async def test_validate_flags_segments_against_the_beats(
        client, workspace, monkeypatch):
    _assemble(workspace)

    from reelstudio.agent import llm

    async def fake_chat(config, messages, tools):
        # the reviewer receives the segments listing + midpoint frames
        assert tools == []
        listing = messages[0]["content"][0]["text"]
        ids = [line.split()[1] for line in listing.splitlines()
               if line.strip().startswith("- ")]
        return {"content": json.dumps(
            [{"segment": sid,
              "verdict": "issue" if sid == "s1_ramen" else "ok",
              "note": "wrong subject" if sid == "s1_ramen" else "fair midpoint"}
             for sid in ids])}

    monkeypatch.setattr(llm, "chat", fake_chat)
    resp = await client.post("/reelstudio/api/validate")
    assert resp.status == 200

    report = await _poll(client)
    assert report["state"] == "done", report
    assert report["total"] == 3
    issue = next((f for f in report["findings"] if f["verdict"] == "issue"),
                 None)
    assert issue, json.dumps(report)
    assert issue["segment"] == "s1_ramen"
    assert issue["note"] == "wrong subject"


async def test_validate_without_a_final_cut_reports_the_error(
        client, workspace):
    resp = await client.post("/reelstudio/api/validate")
    assert resp.status == 200
    report = await _poll(client)
    assert report["state"] == "error"
    assert "no final cut" in report["error"]


async def test_validate_rejects_a_second_run_while_one_is_running(
        client, workspace, monkeypatch):
    _assemble(workspace)
    from reelstudio.agent import llm

    release = asyncio.Event()

    async def slow_chat(config, messages, tools):
        await release.wait()
        return {"content": "[]"}

    monkeypatch.setattr(llm, "chat", slow_chat)
    await client.post("/reelstudio/api/validate")
    # wait until the first run is inside its LLM call, then re-try
    started = False
    for _ in range(50):
        report = (await (await client.get("/reelstudio/api/validate")).json()
                  )["report"]
        if report.get("state") == "running":
            started = True
            break
        await asyncio.sleep(0.1)
    assert started
    resp = await client.post("/reelstudio/api/validate")
    assert resp.status == 409
    release.set()
    await _poll(client)


@pytest.fixture(autouse=True)
def _hermetic_llm(monkeypatch):
    """The validate run must never touch the real gateway."""
    from reelstudio.agent import llm
    monkeypatch.setattr(llm, "chat",
                        lambda *a, **k: (_ for _ in ()).throw(
                            AssertionError("gateway reached")))
