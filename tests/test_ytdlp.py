"""URL audio import: the endpoint lands yt-dlp output in audio/ and rejects
bad input. yt-dlp is a third-party boundary — the stub below fakes exactly
its contract with us (write the -o file, print the final path)."""

STUB = '''#!/usr/bin/env python3
import sys
args = sys.argv[1:]
tmpl = args[args.index("-o") + 1]
path = tmpl.replace("%(ext)s", "mp3")
open(path, "wb").write(b"ID3stub")
print(path)
'''


def _stub_ytdlp(tmp_path, monkeypatch):
    stub = tmp_path / "yt-dlp-stub"
    stub.write_text(STUB)
    stub.chmod(0o755)
    monkeypatch.setenv("REELSTUDIO_YTDLP", str(stub))
    return stub


async def test_grab_lands_file_in_audio_library(client, workspace, tmp_path,
                                                monkeypatch):
    _stub_ytdlp(tmp_path, monkeypatch)

    resp = await client.post("/reelstudio/api/audio/import", json={
        "url": "https://www.youtube.com/watch?v=JaWD8", "name": "Ref Track"})
    assert resp.status == 200
    body = await resp.json()
    assert body["path"] == "audio/Ref_Track.mp3"
    assert (workspace / "audio" / "Ref_Track.mp3").read_bytes() == b"ID3stub"


async def test_grab_rejects_non_http_and_missing_url(client, workspace,
                                                     tmp_path, monkeypatch):
    _stub_ytdlp(tmp_path, monkeypatch)

    for payload in ({"url": "ftp://x/y"}, {"url": "-o /etc/passwd"}, {}):
        resp = await client.post("/reelstudio/api/audio/import", json=payload)
        assert resp.status == 400
        assert "problems" in await resp.json()
    assert not (workspace / "audio").exists()
