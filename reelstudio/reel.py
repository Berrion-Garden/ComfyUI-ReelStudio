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
    """reel.py beside reel.yaml, or the ONE shared copy at the studio root
    (scene dirs carry data; the pipeline is never duplicated)."""
    for dir in (workspace, workspace.parent, workspace.parent.parent):
        script = dir / "reel.py"
        if script.is_file():
            return script
    raise FileNotFoundError(
        f"reel.py not found beside reel.yaml or at the studio root "
        f"(looked from {workspace}) — the pipeline script is the single "
        "source of truth for the pipeline")


def _spawn(env: dict | None = None) -> dict | None:
    """The subprocess env: inherit everything, overlay the studio's extras
    (REELSTUDIO_JOB_ID — the pipeline stamps it on what it produces)."""
    import os

    if env is None:
        return None
    return {**os.environ, **env}


async def run_async(workspace: Path, cmd: str, args: list[str] | None = None,
                    env: dict | None = None) -> str:
    """Run `python3 reel.py <cmd> [args...]` from the workspace; returns the
    last lines of its output (the per-scene DONE/overlay lines live there)."""
    script = workspace_script(workspace)
    proc = await asyncio.create_subprocess_exec(
        sys.executable, str(script), cmd, *(args or []),
        cwd=str(workspace),
        env=_spawn(env),
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


def run_sync(workspace: Path, cmd: str, args: list[str] | None = None,
             env: dict | None = None) -> str:
    """Blocking twin of run_async for thread-pool executors."""
    import subprocess

    script = workspace_script(workspace)
    proc = subprocess.run(
        [sys.executable, str(script), cmd, *(args or [])],
        cwd=str(workspace), capture_output=True, text=True, env=_spawn(env))
    if proc.returncode != 0:
        raise ReelScriptError(
            f"reel.py {cmd} failed (exit {proc.returncode}):\n"
            f"{tail(proc.stdout + proc.stderr)}")
    return proc.stdout
