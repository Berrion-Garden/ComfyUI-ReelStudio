"""Agent loop + tools against a scripted fake gateway (same isolated
endpoint as the fake ComfyUI — the test server plays both roles)."""

import json

from conftest import YAML_BODY

GATEWAY_PATH = "/v1/chat/completions"


def scripted_gateway(responses: list[dict]):
    """A /v1/chat/completions that replays scripted assistant messages."""
    from aiohttp import web

    state = {"calls": []}

    async def completions(request: web.Request) -> web.Response:
        body = await request.json()
        state["calls"].append(body)
        message = responses[min(len(state["calls"]) - 1, len(responses) - 1)]
        return web.json_response({"choices": [{"message": message}]})

    app = web.Application()
    app.router.add_post(GATEWAY_PATH, completions)
    return app, state


def assistant_text(text: str) -> dict:
    return {"role": "assistant", "content": text, "tool_calls": None}


def assistant_tool(call_id: str, name: str, args: dict) -> dict:
    return {"role": "assistant", "content": None, "tool_calls": [
        {"id": call_id, "type": "function",
         "function": {"name": name, "arguments": json.dumps(args)}}]}


async def test_toolbox_update_yaml_and_staleness(config):
    from reelstudio.agent.tools import ToolBox
    from reelstudio.app import ReelStudio

    state = ReelStudio(config)
    box = ToolBox(state)
    raw = config.yaml_path.read_text()
    result = json.loads(await box.call("update_yaml",
                                       {"text": raw.replace("noodles", "soup")}))
    assert result["saved"] is True
    assert "soup" in config.yaml_path.read_text()

    broken = raw.replace("next: s2_bowldrop", "next: nope")
    result = json.loads(await box.call("update_yaml", {"text": broken}))
    assert "error" in result and "chain break" in result["error"]
    # the broken text never touched disk
    assert "soup" in config.yaml_path.read_text()


async def test_agent_loop_edits_yaml_and_streams_events(config, workspace):
    from dataclasses import replace

    from reelstudio.agent.loop import run
    from reelstudio.agent.tools import ToolBox
    from reelstudio.app import ReelStudio
    from aiohttp.test_utils import TestClient, TestServer

    edited = YAML_BODY.format(comfy="http://127.0.0.1:8288", workspace=workspace) \
        .replace("noodles", "soup")
    script = [
        assistant_tool("c1", "get_yaml", {}),
        assistant_tool("c2", "update_yaml", {"text": edited}),
        assistant_text("Changed the ramen to soup and flagged scene s1_ramen for re-render."),
    ]
    app, gw_state = scripted_gateway(script)
    server = TestServer(app, host="127.0.0.1", port=8288)
    await server.start_server()

    state = ReelStudio(replace(config, agent_base_url="http://127.0.0.1:8288/v1"))
    events = [e async for e in run(state.config, [], ToolBox(state))]

    kinds = [e["type"] for e in events]
    assert kinds == ["tool_call", "tool_result", "tool_call", "tool_result",
                     "message", "done"]
    assert "soup" in config.yaml_path.read_text()
    final = events[-2]
    assert "s1_ramen" in final["text"]
    await server.close()


async def test_agent_chat_route_sse_scripted(config, workspace):
    from aiohttp.test_utils import TestClient, TestServer

    from reelstudio.app import STATE_KEY, create_app

    app, _ = scripted_gateway([assistant_text("roger that")])
    gw = TestServer(app, host="127.0.0.1", port=8288)
    await gw.start_server()

    # the reelstudio app's agent_base_url must point at the fake gateway
    cfg = config
    from dataclasses import replace

    cfg = replace(cfg, agent_base_url="http://127.0.0.1:8288/v1")
    tc = TestClient(TestServer(create_app(cfg)))
    await tc.start_server()

    resp = await tc.post("/reelstudio/api/agent/chat",
                         json={"message": "hello agent"})
    assert resp.status == 200
    assert resp.headers["Content-Type"].startswith("text/event-stream")
    events = []
    async for line in resp.content:
        line = line.decode().strip()
        if line.startswith("data: "):
            events.append(json.loads(line[6:]))
    kinds = [e["type"] for e in events]
    assert kinds == ["message", "done"]
    assert events[0]["text"] == "roger that"
    await tc.close()
    await gw.close()
