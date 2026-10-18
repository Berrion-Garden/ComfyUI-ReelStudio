"""Mount the Reel Studio app onto ComfyUI's PromptServer.

This is the only production adapter: the same handlers that run standalone in
tests are registered on Comfy's aiohttp server under /reelstudio, plus the
built web UI served from ./web/dist.
"""

from pathlib import Path

from .app import STATE_KEY, create_app
from .config import load_config

UI_DIST = Path(__file__).resolve().parent.parent / "web" / "dist"


def mount_on_prompt_server():
    from server import PromptServer  # only importable inside ComfyUI

    app = create_app(load_config())
    server = PromptServer.instance
    # handlers read state from request.app — that is ComfyUI's app here, so
    # the state moves with the routes (and the job worker lifecycle too)
    server.app[STATE_KEY] = app[STATE_KEY]
    for route in app.router.routes():
        server.app.router.add_route(route.method, route.resource.canonical, route.handler)
    # app-level behavior travels with the routes too: without the middleware
    # copy, ReelStudioError 4xx responses become 500s in production
    server.app.middlewares.extend(app.middlewares)
    server.app.on_startup.append(app[STATE_KEY].start)
    server.app.on_cleanup.append(app[STATE_KEY].close)
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

    # no-cache: a stale index.html references bundles that no longer exist
    return web.FileResponse(UI_DIST / "index.html",
                            headers={"Cache-Control": "no-cache"})


def _static(request):
    from aiohttp import web

    tail = request.match_info.get("tail", "")
    target = (UI_DIST / tail).resolve()
    if not target.is_relative_to(UI_DIST) or not target.is_file():
        # SPA fallback: unknown paths render the app shell
        return web.FileResponse(UI_DIST / "index.html")
    return web.FileResponse(target)


def main():
    """Standalone dev server: the same app, no ComfyUI around it.
    `reelstudio serve` (installed script) or `python -m reelstudio.server`."""
    import argparse

    from aiohttp import web

    parser = argparse.ArgumentParser(
        prog="reelstudio", description="Reel Studio standalone server")
    parser.add_argument("cmd", nargs="?", default="serve",
                        help="only 'serve' today")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8287)
    args = parser.parse_args()
    app = create_app(load_config())
    if UI_DIST.exists():
        app.router.add_get("/reelstudio", _index)
        app.router.add_get("/reelstudio/{tail:.*}", _static)
    web.run_app(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
