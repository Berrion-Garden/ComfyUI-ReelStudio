"""Reel Studio web app: routes, job queue, artifact serving.

create_app() builds a standalone aiohttp application — that is what tests run
against the isolated endpoint (127.0.0.1:8288) and what server.py mounts onto
ComfyUI's PromptServer in production. One handler set, one adapter.
"""

import asyncio
import json
import subprocess
import urllib.parse
import uuid
from pathlib import Path

from aiohttp import web

from . import manifest as manifest_mod
from . import assets as assets_mod
from . import generate, timeline
from . import audio as audio_mod
from . import reel as reel_pipeline
from .agent.loop import run as agent_run
from .agent.tools import ToolBox
from .config import Config
from .errors import ForbiddenError, NotFoundError, ReelStudioError, ValidationError
from .project import load as load_project
from .readmodel import asset_view, project_view

API = "/reelstudio/api"


class RenderJob:
    def __init__(self, kind: str, target: str):
        self.id = uuid.uuid4().hex[:12]
        self.kind = kind          # scene | music | assemble
        self.target = target
        self.status = "queued"    # queued | running | done | error
        self.error: str | None = None
        self.result: str | None = None

    def view(self) -> dict:
        return {"id": self.id, "kind": self.kind, "target": self.target,
                "status": self.status, "error": self.error,
                "result": self.result}


class ReelStudio:
    """App state: config, the loaded project, and the render queue."""

    def __init__(self, config: Config):
        self.config = config
        self.jobs: dict[str, RenderJob] = {}
        self._queue: asyncio.Queue[RenderJob] = asyncio.Queue()
        self._worker: asyncio.Task | None = None

    # ------------------------------------------------------------ project --
    def project(self):
        return load_project(self.config)

    # -------------------------------------------------------------- jobs ---
    async def start(self, app):
        self._worker = asyncio.create_task(self._work(), name="reelstudio-worker")

    async def close(self, app):
        if self._worker:
            self._worker.cancel()

    def enqueue(self, kind: str, target: str) -> RenderJob:
        job = RenderJob(kind, target)
        self.jobs[job.id] = job
        self._queue.put_nowait(job)
        return job

    async def _work(self):
        # one render at a time: the GPU node is a single resource
        while True:
            job = await self._queue.get()
            job.status = "running"
            try:
                project = self.project()
                job.result = await asyncio.to_thread(
                    generate.run_job, project, None,
                    self.config.workspace.as_posix() + "/.work",
                    job.kind, job.target)
            except Exception as e:  # noqa: BLE001 - job errors surface in the UI
                job.status = "error"
                job.error = str(e)
            else:
                job.status = "done"
            self._queue.task_done()


# ------------------------------------------------------------- handlers ----
STATE_KEY = web.AppKey("reelstudio", ReelStudio)
def _state(request: web.Request) -> ReelStudio:
    return request.app[STATE_KEY]


def _json_error(e: ReelStudioError):
    status = 404 if isinstance(e, NotFoundError) else 400
    if isinstance(e, ForbiddenError):
        status = 403
    body = {"error": str(e)}
    if isinstance(e, ValidationError):
        body["problems"] = e.problems
    return web.json_response(body, status=status)


async def get_project(request: web.Request) -> web.Response:
    try:
        state = _state(request)
        return web.json_response(project_view(state, api=API))
    except ValidationError as e:
        return _json_error(e)


async def get_yaml(request: web.Request) -> web.Response:
    state = _state(request)
    return web.json_response({"text": state.config.yaml_path.read_text()})


async def put_yaml(request: web.Request) -> web.Response:
    state = _state(request)
    body = await request.json()
    text = body.get("text")
    if not isinstance(text, str):
        return web.json_response({"error": "body must be {text: yaml}"}, status=400)
    project = state.project()
    try:
        warnings = project.save(text)
    except ValidationError as e:
        return _json_error(e)
    return web.json_response({"saved": True, "warnings": warnings})


async def post_render(request: web.Request) -> web.Response:
    state = _state(request)
    body = await request.json()
    specs = generate.plan(state.project(), "scene", body)
    jobs = [state.enqueue(kind, target) for kind, target in specs]
    return web.json_response({"jobs": [j.view() for j in jobs]})


async def post_music(request: web.Request) -> web.Response:
    state = _state(request)
    body = await request.json()
    specs = generate.plan(state.project(), "music",
                          {"name": body.get("name")})
    jobs = [state.enqueue(kind, target) for kind, target in specs]
    return web.json_response({"jobs": [j.view() for j in jobs]})


async def post_assemble(request: web.Request) -> web.Response:
    state = _state(request)
    body = await request.json() if request.can_read_body else {}
    specs = generate.plan(state.project(), "assemble", body)
    jobs = [state.enqueue(kind, target) for kind, target in specs]
    return web.json_response({"jobs": [j.view() for j in jobs]})


async def get_jobs(request: web.Request) -> web.Response:
    state = _state(request)
    return web.json_response({"jobs": [j.view() for j in state.jobs.values()]})


async def get_scene_artifact(request: web.Request) -> web.Response:
    state = _state(request)
    project = state.project()
    sid = request.match_info["scene_id"]
    kind = request.match_info["kind"]
    scene = project.scene(sid)
    if scene is None:
        raise NotFoundError(f"unknown scene {sid!r}")

    if kind == "video":
        file = manifest_mod.deliverable(project.meta["reel_dir"], sid)
        if file is None:
            raise NotFoundError(f"scene {sid!r} has no render")
        return web.FileResponse(Path(file))

    if kind == "sfx":
        split = audio_mod.split_path(project, sid)
        if not split.is_file():
            raise NotFoundError(
                f"scene {sid!r} has no audio split (reel.py sfx {sid})")
        return web.FileResponse(split)

    if kind in ("thumb_first", "thumb_last"):
        anchor = scene["video"].get("first" if kind == "thumb_first" else "last")
        resolved = timeline.resolve_anchor(project, anchor)
        if resolved["kind"] == "none":
            raise NotFoundError(f"scene {sid!r} has no {kind[6:]} anchor")
        if resolved["kind"] == "prev_last":
            prev = project.previous(sid)
            src = manifest_mod.deliverable(project.meta["reel_dir"], prev["id"])
            if src is None:
                raise NotFoundError(f"upstream {prev['id']} has no render")
            cache = Path(state.config.workspace) / ".work" / "thumbs"
            cache.mkdir(parents=True, exist_ok=True)
            png = cache / f"{prev['id']}.png"
            if not png.exists() or Path(src).stat().st_mtime > png.stat().st_mtime:
                subprocess.run(
                    ["/usr/bin/ffmpeg", "-y", "-v", "error", "-sseof", "-0.05",
                     "-i", str(src), "-frames:v", "1", str(png)],
                    check=True)
            return web.FileResponse(png)
        if resolved["kind"] == "still":
            path = resolved.get("path")
            if not path or not Path(path).exists():
                raise NotFoundError(f"still file for {sid!r} missing")
            return web.FileResponse(Path(path))
        return web.FileResponse(Path(resolved["path"]))

    raise NotFoundError(f"unknown artifact kind {kind!r}")


async def get_music_artifact(request: web.Request) -> web.Response:
    """Rendered audio for a music segment (range-capable FileResponse)."""
    state = _state(request)
    project = state.project()
    file = manifest_mod.music_file(project.meta["reel_dir"],
                                   request.match_info["name"])
    if file is None:
        raise NotFoundError("segment not rendered yet")
    return web.FileResponse(Path(file))


async def get_audio_artifact(request: web.Request) -> web.Response:
    """An `audio:` track's source file, as declared in reel.yaml.

    The index — not a client-supplied path — selects the file, so the
    operator's music library stays reachable without widening the asset roots.
    """
    state = _state(request)
    project = state.project()
    try:
        t = audio_mod.track(project, int(request.match_info["index"]))
    except ValueError:
        raise NotFoundError("no such audio track")
    file = Path(t["file"]).expanduser()
    if not file.is_file():
        raise NotFoundError("audio file missing")
    return web.FileResponse(file)


async def get_audio_peaks(request: web.Request) -> web.Response:
    """Waveform envelope for the audio graph lane."""
    state = _state(request)
    project = state.project()
    try:
        index = int(request.match_info["index"])
    except ValueError:
        raise NotFoundError("no such audio track")
    try:
        buckets = min(int(request.query.get("buckets", "600")), 4000)
    except ValueError:
        buckets = 600
    peaks = await asyncio.to_thread(audio_mod.peaks, project, index, buckets)
    return web.json_response({"peaks": peaks})


async def put_audio_track(request: web.Request) -> web.Response:
    """Update one track's timestamp note (at/seek/gain/fades) in reel.yaml."""
    state = _state(request)
    project = state.project()
    body = await request.json()
    try:
        index = int(request.match_info["index"])
    except ValueError:
        raise NotFoundError("no such audio track")
    try:
        t = audio_mod.update_track(project, state.config, index, body)
    except ValueError:
        raise NotFoundError("no such audio track")
    return web.json_response(t)


async def get_sfx_board(request: web.Request) -> web.Response:
    """Per-scene sound-effects facts: the soundscape prompt, the bell asset,
    and the split audio (waveform peaks optional via ?peaks=<buckets>)."""
    state = _state(request)
    project = state.project()
    try:
        buckets = max(0, int(request.query.get("peaks", "0")))
    except ValueError:
        buckets = 0
    items = []
    for s in project.scenes:
        se = s.get("sound_effects") or {}
        sid = s["id"]
        split = audio_mod.split_path(project, sid)
        item = {
            "id": sid,
            "soundscape": str(se.get("soundscape") or ""),
            "bell": se.get("bell"),
            "bell_at": se.get("bell_at"),
            "split": f"{API}/scene/{sid}/artifact/sfx" if split.is_file() else None,
            "peaks": None,
            "assets": [],
        }
        for ev in audio_mod.sfx_events(project, sid):
            item["assets"].append({
                "asset": ev["asset"], "at": ev["at"], "gain": ev["gain"],
                "url": (f"{API}/asset/file?path=sfx/{ev['file']}"
                        if ev["file"] else None),
            })
        if buckets and item["split"]:
            item["peaks"] = await asyncio.to_thread(
                audio_mod.peaks_for_path, split, buckets)
        items.append(item)
    return web.json_response({"scenes": items})


async def post_sfx_event(request: web.Request) -> web.Response:
    """Place a sound-effect asset on the timeline: {scene_id, asset, at, gain}."""
    state = _state(request)
    body = await request.json()
    return web.json_response(audio_mod.place_sfx_event(
        state.project(), state.config, str(body.get("scene_id", "")), body))


async def delete_sfx_event(request: web.Request) -> web.Response:
    """Remove a placed one-shot: {scene_id, index}."""
    state = _state(request)
    body = await request.json()
    try:
        index = int(body.get("index"))
    except (TypeError, ValueError):
        raise ValidationError(["index must be an integer"])
    return web.json_response(audio_mod.remove_sfx_event(
        state.project(), state.config, str(body.get("scene_id", "")), index))


async def get_bell_artifact(request: web.Request) -> web.Response:
    """The synth bell sample, rendered by reel.py (one bell implementation)."""
    state = _state(request)
    project = state.project()
    cache = Path(project.meta.get("work", "")) / "bell.wav"
    if not cache.is_file():
        await asyncio.to_thread(
            reel_pipeline.run_sync,
            Path(state.config.workspace), "bell", [str(cache)])
    return web.FileResponse(cache)


async def get_assets(request: web.Request) -> web.Response:
    state = _state(request)
    data = asset_view(state)
    for group in data["groups"].values():
        for a in group:
            a["url"] = f"{API}/asset/file?path={urllib.parse.quote(a['path'], safe='')}"
    return web.json_response(data)


async def get_asset_file(request: web.Request) -> web.Response:
    state = _state(request)
    project = state.project()
    target = assets_mod.asset_file(request.query.get("path", ""), [
        state.config.workspace, project.meta["still_dir"], project.meta["reel_dir"],
    ])
    if not target.is_file():
        raise NotFoundError(f"no such asset: {target.name}")
    return web.FileResponse(target)


async def put_asset_labels(request: web.Request) -> web.Response:
    """Rewrite one asset's declared labels: {path, labels: [..]}."""
    state = _state(request)
    body = await request.json()
    labels = body.get("labels")
    if not isinstance(labels, list) or not all(isinstance(x, str) for x in labels):
        raise ValidationError(["labels must be a list of strings"])
    project = state.project()
    result = await asyncio.to_thread(
        assets_mod.set_labels, state.config.workspace,
        project.meta["still_dir"], str(body.get("path", "")), labels)
    return web.json_response(result)


async def delete_asset(request: web.Request) -> web.Response:
    """The operator's ✗ on a non-verified generation: delete the file and
    its label entry. Only assets labelled non-verified are deletable."""
    state = _state(request)
    body = await request.json()
    project = state.project()
    target = assets_mod.asset_file(str(body.get("path", "")), [
        state.config.workspace, project.meta["still_dir"], project.meta["reel_dir"],
    ])
    index = assets_mod.index_assets(state.config.workspace, project)
    item = next((a for items in index["groups"].values() for a in items
                 if a["path"] == str(target)), None)
    if item is None or "non-verified" not in item["labels"]:
        raise ForbiddenError("only assets labelled non-verified can be deleted")
    await asyncio.to_thread(target.unlink)
    await asyncio.to_thread(
        assets_mod.set_labels, state.config.workspace,
        project.meta["still_dir"], str(target), [])
    return web.json_response({"deleted": target.name})


async def get_final(request: web.Request) -> web.Response:
    state = _state(request)
    final = state.project().meta.get("final")
    if not final or not Path(final).exists():
        raise NotFoundError("no final production yet — run assemble")
    return web.FileResponse(Path(final))


async def post_agent_chat(request: web.Request) -> web.StreamResponse:
    state = _state(request)
    body = await request.json()
    history = body.get("history") or []
    user_text = (body.get("message") or "").strip()
    if not user_text:
        return web.json_response({"error": "message required"}, status=400)
    history = [*history, {"role": "user", "content": user_text}]
    selected = body.get("selected") if isinstance(body.get("selected"), dict) else None

    resp = web.StreamResponse(headers={
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
    })
    await resp.prepare(request)
    try:
        async for event in agent_run(state.config, history,
                                     ToolBox(state, selected=selected)):
            await resp.write(f"data: {json.dumps(event, ensure_ascii=False)}\n\n".encode())
    except Exception as e:  # noqa: BLE001 - stream the failure to the UI
        await resp.write(f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n".encode())
        await resp.write(b"data: {\"type\": \"done\"}\n\n")
    await resp.write_eof()
    return resp


async def post_manifest_adopt(request: web.Request) -> web.Response:
    """Declare pre-app renders current so staleness starts from truth."""
    state = _state(request)
    project = state.project()
    adopted = manifest_mod.adopt_existing(project.meta["reel_dir"], project)
    return web.json_response({"adopted": adopted})


def create_app(config: Config) -> web.Application:
    app = web.Application()

    @web.middleware
    async def error_middleware(request: web.Request, handler):
        try:
            return await handler(request)
        except ReelStudioError as e:
            return _json_error(e)
        except web.HTTPException:
            raise

    app.middlewares.append(error_middleware)
    state = ReelStudio(config)
    app[STATE_KEY] = state
    app.router.add_get(f"{API}/project", get_project)
    app.router.add_get(f"{API}/yaml", get_yaml)
    app.router.add_put(f"{API}/yaml", put_yaml)
    app.router.add_post(f"{API}/render", post_render)
    app.router.add_post(f"{API}/music", post_music)
    app.router.add_post(f"{API}/assemble", post_assemble)
    app.router.add_get(f"{API}/jobs", get_jobs)
    app.router.add_get(f"{API}/final", get_final)
    app.router.add_get(f"{API}/assets", get_assets)
    app.router.add_put(f"{API}/assets/labels", put_asset_labels)
    app.router.add_delete(f"{API}/asset", delete_asset)
    app.router.add_get(f"{API}/asset/file", get_asset_file)
    app.router.add_get(f"{API}/music/{{name}}/artifact", get_music_artifact)
    app.router.add_get(f"{API}/audio/{{index}}/artifact", get_audio_artifact)
    app.router.add_get(f"{API}/audio/{{index}}/peaks", get_audio_peaks)
    app.router.add_put(f"{API}/audio/{{index}}", put_audio_track)
    app.router.add_get(f"{API}/bell/artifact", get_bell_artifact)
    app.router.add_get(f"{API}/sfx/board", get_sfx_board)
    app.router.add_post(f"{API}/sfx/board", post_sfx_event)
    app.router.add_delete(f"{API}/sfx/board", delete_sfx_event)
    app.router.add_post(f"{API}/manifest/adopt", post_manifest_adopt)
    app.router.add_get(f"{API}/scene/{{scene_id}}/artifact/{{kind}}", get_scene_artifact)
    app.router.add_post(f"{API}/agent/chat", post_agent_chat)
    app.on_startup.append(state.start)
    app.on_cleanup.append(state.close)
    return app
