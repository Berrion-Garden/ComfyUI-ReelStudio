"""The execution seam to reel.py — the ONLY pipeline implementation.

reel.py (in the workspace) is the single source of truth for touching
ComfyUI/ffmpeg: H3 scene renders, freeze post, Music3 generation, and the
final mix. This module runs it as a subprocess and reports back the log tail;
the studio never re-implements any of it.
"""

import asyncio
import sys
from pathlib import Path


class ReelScriptError(RuntimeError):
    """reel.py exited non-zero; the message carries the log tail."""


def workspace_script(workspace: Path) -> Path:
    """The workspace's reel.py; the operator's pipeline lives beside reel.yaml."""
    script = workspace / "reel.py"
    if not script.is_file():
        raise FileNotFoundError(
            f"reel.py not found in the workspace ({workspace}) — the pipeline "
            "script must sit beside reel.yaml")
    return script


async def run_async(workspace: Path, cmd: str, args: list[str] | None = None) -> str:
    """Run `python3 reel.py <cmd> [args...]` from the workspace; returns the
    last lines of its output (the per-scene DONE/overlay lines live there)."""
    script = workspace_script(workspace)
    proc = await asyncio.create_subprocess_exec(
        sys.executable, str(script), cmd, *(args or []),
        cwd=str(workspace),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    out, _ = await proc.communicate()
    text = out.decode(errors="replace")
    if proc.returncode != 0:
        raise ReelScriptError(
            f"reel.py {cmd} failed (exit {proc.returncode}):\n{tail(text)}")
    return text


def tail(text: str, lines: int = 10) -> str:
    return "\n".join(text.strip().splitlines()[-lines:])


def run_sync(workspace: Path, cmd: str, args: list[str] | None = None) -> str:
    """Blocking twin of run_async for thread-pool executors."""
    import subprocess

    script = workspace_script(workspace)
    proc = subprocess.run(
        [sys.executable, str(script), cmd, *(args or [])],
        cwd=str(workspace), capture_output=True, text=True)
    if proc.returncode != 0:
        raise ReelScriptError(
            f"reel.py {cmd} failed (exit {proc.returncode}):\n"
            f"{tail(proc.stdout + proc.stderr)}")
    return proc.stdout
