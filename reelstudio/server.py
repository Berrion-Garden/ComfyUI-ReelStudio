"""Mount the Reel Studio app onto ComfyUI's PromptServer.

This is the only production adapter: the same handlers that run standalone in
tests are registered on Comfy's aiohttp server under /reelstudio, plus the
built web UI served from ./web/dist.
"""

from pathlib import Path

from .app import create_app
from .config import load_config

UI_DIST = Path(__file__).resolve().parent.parent / "web" / "dist"


def mount_on_prompt_server():
    from server import PromptServer  # only importable inside ComfyUI

    app = create_app(load_config())
    server = PromptServer.instance
    for route in app.router.routes():
        server.app.router.add_route(route.method, route.resource.canonical, route.handler)
    if UI_DIST.exists():
        server.app.router.add_get("/reelstudio", _index)
        server.app.router.add_get("/reelstudio/{tail:.*}", _static)
    else:
        server.app.router.add_get("/reelstudio", _build_hint)


def _build_hint(_request):
    from aiohttp import web

    return web.Response(
        status=503, text="web UI not built — run `npm ci && npm run build` in frontend/ "
                         "and copy frontend/dist to web/dist")


def _index(_request):
    from aiohttp import web

    return web.FileResponse(UI_DIST / "index.html")


def _static(request):
    from aiohttp import web

    tail = request.match_info.get("tail", "")
    target = (UI_DIST / tail).resolve()
    if not str(target).startswith(str(UI_DIST)) or not target.is_file():
        # SPA fallback: unknown paths render the app shell
        return web.FileResponse(UI_DIST / "index.html")
    return web.FileResponse(target)
