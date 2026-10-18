"""The job journal and provenance claw-back: durable job records, the
`job:<id>` label lookup, the manifest lookup, and the PNG prompt chunk."""

import json
import struct

import pytest

from reelstudio import jobs as jobs_mod
from reelstudio.config import Config


@pytest.fixture
def config(tmp_path):
    return Config(workspace=tmp_path, agent_model="writer",
                  agent_base_url="https://x/v1")


def png_with_prompt(path, graph: dict):
    """A real PNG stream carrying ComfyUI's `prompt` tEXt chunk."""
    payload = json.dumps(graph).encode()
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    chunks = b"\x89PNG\r\n\x1a\n"
    for typ, data in [(b"IHDR", ihdr), (b"tEXt", b"prompt\x00" + payload),
                      (b"IEND", b"")]:
        chunks += struct.pack(">I", len(data)) + typ + data
        chunks += struct.pack(">I", 0)  # crc unchecked by our reader
    path.write_bytes(chunks)


GRAPH = {
    "5": {"class_type": "TextEncodeQwenImage21",
          "inputs": {"prompt": "a were-tiger mid-dunk", "negative_prompt": "blurry"}},
    "8": {"class_type": "KSampler", "inputs": {"seed": 3252759590279801836, "steps": 8}},
    "1": {"class_type": "UNETLoader", "inputs": {"unet_name": "qwen_int8.safetensors"}},
    "7": {"class_type": "EmptyLatentImage", "inputs": {"width": 768, "height": 768}},
}


async def test_journal_roundtrip_and_last_wins(config):
    jobs_mod.record(config, id="abc", kind="still", target="park", status="queued")
    jobs_mod.record(config, id="abc", status="done", result="/x/y.png", seed=None)
    # a torn tail line is skipped, not fatal
    with open(jobs_mod.journal_path(config), "a") as fh:
        fh.write('{"id": "tor')
    got = jobs_mod.load(config)
    assert got["abc"]["status"] == "done"
    assert got["abc"]["result"] == "/x/y.png"


def test_png_prompt_chunk(tmp_path):
    p = tmp_path / "x.png"
    png_with_prompt(p, GRAPH)
    s = jobs_mod.summarize_prompt(jobs_mod.png_prompt(p))
    assert s["prompt"] == "a were-tiger mid-dunk"
    assert s["negative_prompt"] == "blurry"
    assert s["seed"] == 3252759590279801836
    assert s["steps"] == 8
    assert s["unet"] == "qwen_int8.safetensors"
    assert s["width"] == 768
    # an image without the chunk (or an empty graph) summarizes to nothing
    plain = tmp_path / "plain.png"
    png_with_prompt(plain, {})
    assert jobs_mod.png_prompt(plain) == {}
    assert jobs_mod.summarize_prompt({}) is None
    assert jobs_mod.summarize_prompt(None) is None


def test_provenance_via_label(tmp_path, config):
    (config.workspace / "characters" / "tony").mkdir(parents=True)
    img = config.workspace / "characters" / "tony" / "tony_sheet01_00001.png"
    png_with_prompt(img, GRAPH)
    (config.workspace / "assets.yaml").write_text(
        "labels:\n  characters/tony/tony_sheet01_00001.png:\n"
        "  - char:tony\n  - non-verified\n  - job:abc123\n")
    jobs_mod.record(config, id="abc123", kind="sheet", target="tony",
                    status="done", result=str(img))

    prov = jobs_mod.provenance(config, str(img))
    assert prov["job"] == "abc123"
    assert prov["record"]["kind"] == "sheet"
    assert prov["record"]["target"] == "tony"
    assert prov["embedded"]["seed"] == 3252759590279801836
    assert prov["embedded"]["prompt"] == "a were-tiger mid-dunk"


def test_provenance_via_manifest_for_videos(tmp_path, config, monkeypatch):
    reel_dir = tmp_path / "out" / "h3_reel"
    reel_dir.mkdir(parents=True)
    video = reel_dir / "s1_ramen_00001_.mp4"
    video.write_bytes(b"fake mp4")
    (reel_dir / ".reelstudio_manifest.json").write_text(json.dumps({
        "scenes": {"s1_ramen": {
            "video": {"kind": "video", "path": {"file": "s1_ramen_00001_.mp4"}},
            "frames": 107, "job": "deadbeef"}},
        "music": {}}))

    class StubProject:
        meta = {"still_dir": str(tmp_path / "stills"),
                "reel_dir": str(reel_dir)}

    monkeypatch.setattr("reelstudio.project.load",
                        lambda config: StubProject())

    prov = jobs_mod.provenance(config, str(video))
    assert prov["job"] == "deadbeef"
    assert prov["record"] is None      # journal knows nothing of this run
    assert prov["embedded"] is None    # mp4 carries no prompt chunk


def test_provenance_unknown_file(config):
    from reelstudio.errors import ForbiddenError

    with pytest.raises(ForbiddenError):  # relative paths resolve outside the roots
        jobs_mod.provenance(config, "nope.png")
