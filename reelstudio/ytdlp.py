"""URL audio import — grab a reference track off the web into the scene's
audio/ library. Wraps the box's verified yt-dlp build (see
~/MediaTools-mac/README.md) so imported tracks are ordinary audio/ assets:
the library index picks them up and an `audio:` entry in reel.yaml plays them.
"""

import os
import re
import shutil
import subprocess
from pathlib import Path

from .errors import ValidationError

FF = "/usr/bin/ffmpeg"  # same convention as audio.py

DOWNLOAD_TIMEOUT = 900  # a slow connection needs real minutes


def binary() -> str:
    """The yt-dlp to run: REELSTUDIO_YTDLP first, then this box's
    checksum-verified MediaTools build (kept current), then PATH."""
    env = os.environ.get("REELSTUDIO_YTDLP", "")
    if env:
        return env
    bundled = Path.home() / "MediaTools-mac" / "yt-dlp-linux"
    if bundled.is_file() and os.access(bundled, os.X_OK):
        return str(bundled)
    found = shutil.which("yt-dlp")
    if not found:
        raise ValidationError(
            ["no yt-dlp found — install it or set REELSTUDIO_YTDLP"])
    return found


def _clean(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", name).strip("._") or "track"


def grab(workspace: Path, url: str, name: str | None = None) -> Path:
    """Download `url` as MP3 into `<workspace>/audio/` and return the file.

    `name` fixes the filename (extension appended by yt-dlp); without it the
    video title is used. Only http(s) URLs — the flag grammar of other
    yt-dlp targets must never be reachable as a URL.
    """
    url = url.strip()
    if not re.fullmatch(r"https?://[^\s]+", url) or len(url) > 2048:
        raise ValidationError(["url must be an http(s) URL"])
    stem = _clean(name) if name else "%(title)s"
    out_dir = Path(workspace) / "audio"
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        binary(),
        "--no-warnings", "--no-progress",  # ANSI stripped from stderr below
        "-x", "--audio-format", "mp3", "--audio-quality", "0",
        "--ffmpeg-location", str(Path(FF).parent),
        "-o", str(out_dir / f"{stem}.%(ext)s"),
        "--print", "after_move:filepath",
        url,
    ]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=DOWNLOAD_TIMEOUT)
    except subprocess.TimeoutExpired:
        raise ValidationError(["download timed out"])
    if proc.returncode != 0:
        detail = re.sub(r"\x1b\[[0-9;]*m", "", proc.stderr).strip()
        raise ValidationError([f"yt-dlp failed: {detail[-400:]}"])
    printed = [line for line in proc.stdout.splitlines() if line.strip()]
    path = Path(printed[-1]) if printed else None
    if path is None or not path.is_file():
        raise ValidationError(["yt-dlp produced no file"])
    return path
