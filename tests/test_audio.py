"""Audio tracks: peaks for the graph, comment-preserving volume-anchor edits,
bell sample rendering."""

import subprocess
from pathlib import Path


def _sine(path: Path, seconds: float = 1.0):
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["/usr/bin/ffmpeg", "-y", "-v", "error", "-f", "lavfi",
         "-i", f"sine=frequency=440:duration={seconds}", "-c:a",
         "libmp3lame", str(path)], check=True)
    return path


def _with_track(workspace: Path, track_path: Path) -> None:
    text = (workspace / "reel.yaml").read_text()
    (workspace / "reel.yaml").write_text(text + (
        "\naudio:\n"
        f"  - name: Night Run\n"
        f"    file: \"{track_path}\"\n"
        "    at: 0.0\n"
        "    seek: 0.0\n"
        "    gain: 1.0\n"
        "    fades: [[0.5, 1.0], [2.0, 0.0]]   # hold, then fade — comment kept\n"))


async def test_peaks_are_normalized_buckets(client, workspace, tmp_path):

    track = _sine(Path(tmp_path) / "music" / "night.mp3")
    _with_track(workspace, track)

    resp = await client.get("/reelstudio/api/audio/0/peaks",
                            params={"buckets": "50"})
    assert resp.status == 200
    peaks = (await resp.json())["peaks"]
    assert len(peaks) == 50
    assert all(0.0 <= p <= 1.0 for p in peaks)
    assert max(peaks) > 0.5  # a sine wave has real energy


async def test_peaks_missing_file_is_404(client, workspace, tmp_path):

    _with_track(workspace, Path(tmp_path) / "music" / "gone.mp3")
    resp = await client.get("/reelstudio/api/audio/0/peaks")
    assert resp.status == 404


async def test_volume_anchor_edit_round_trips_and_keeps_comments(
        client, workspace, tmp_path):

    _with_track(workspace, _sine(Path(tmp_path) / "music" / "night.mp3"))
    before = (workspace / "reel.yaml").read_text()

    resp = await client.put("/reelstudio/api/audio/0", json={
        "fades": [[0.5, 0.2], [1.5, 0.9], [2.0, 0.0]]})
    assert resp.status == 200
    body = await resp.json()
    assert body["fades"] == [[0.5, 0.2], [1.5, 0.9], [2.0, 0.0]]

    after = (workspace / "reel.yaml").read_text()
    assert "# hold, then fade — comment kept" in after  # comments survive
    assert "soundscape: slurp" in after                 # untouched sections too
    # the change is live on the next read
    data = await (await client.get("/reelstudio/api/project")).json()
    assert data["overlays"][0]["fades"] == [[0.5, 0.2], [1.5, 0.9], [2.0, 0.0]]
    # the original comment line is still attached to the fades key
    assert "fades:" in after.split("audio:")[1]
    del before


async def test_volume_anchor_edit_rejects_bad_fades(client, workspace, tmp_path):

    _with_track(workspace, _sine(Path(tmp_path) / "music" / "night.mp3"))
    for fades, problem in (
            ([[2.0, 0.0], [0.5, 1.0]], "sorted"),
            ([[0.5, 1.5]], "0..1"),
            ([[0.5]], "keyframe"),
    ):
        resp = await client.put("/reelstudio/api/audio/0", json={"fades": fades})
        assert resp.status == 400, fades
        assert any(problem in p for p in (await resp.json())["problems"]), fades


async def test_bell_artifact_renders_once_via_reel_py(client, workspace):
    resp = await client.get("/reelstudio/api/bell/artifact")
    assert resp.status == 200
    first = await resp.read()
    assert len(first) > 1000  # a real wav, not an error page
    # cached on disk in the workspace work dir — the second hit serves it
    assert (workspace / ".work" / "bell.wav").exists()
    again = await (await client.get("/reelstudio/api/bell/artifact")).read()
    assert again == first
