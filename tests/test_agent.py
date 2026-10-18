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


async def test_toolbox_labels_tag_refs_without_freezing_derived(config, workspace):
    """The agent tags a pick `ref` and clears non-verified through the same
    write the inspector uses — and derived labels (char:, scene:) stay
    pipeline-owned, never copied into assets.yaml."""
    import yaml as yaml_mod

    from reelstudio.agent.tools import ToolBox
    from reelstudio.app import ReelStudio

    (workspace / "assets.yaml").write_text(
        "labels:\n  stills/opening_still_.png: [scene:s1_ramen, non-verified]\n")
    box = ToolBox(ReelStudio(config))
    still = str(workspace / "stills" / "opening_still_.png")

    out = json.loads(await box.call("update_asset_labels", {
        "path": f"asset:{still}",
        "add": ["ref"], "remove": ["non-verified"]}))
    assert out["labels"] == ["scene:s1_ramen", "ref"]
    text = (workspace / "assets.yaml").read_text()
    assert "ref" in text and "non-verified" not in text
    # only the declared labels are written back — nothing derived frozen in
    assert "used_by" not in text

    # a remove that empties the entry drops it; unknown paths are refused
    out = json.loads(await box.call("update_asset_labels", {
        "path": f"asset:{still}", "remove": ["ref", "scene:s1_ramen"]}))
    assert out["labels"] == []
    refused = json.loads(await box.call("update_asset_labels", {
        "path": str(workspace / "stills" / "../../etc/passwd"), "add": ["x"]}))
    assert "error" in refused
    assert "nothing to do" in await box.call(
        "update_asset_labels", {"path": still})


async def test_toolbox_adopt_renders(config, workspace):
    import shutil

    from reelstudio.agent.tools import ToolBox
    from reelstudio.app import ReelStudio

    reel_dir = workspace / "output" / "reel"
    reel_dir.mkdir(parents=True)
    shutil.copy(workspace / "stills" / "opening_still_.png",
                reel_dir / "s1_ramen_0001.mp4")

    box = ToolBox(ReelStudio(config))
    out = json.loads(await box.call(
        "adopt_renders", {"scene_id": "s1_ramen"}))
    assert out == {"adopted": 1, "scene_id": "s1_ramen"}

    out = json.loads(await box.call("adopt_renders", {"scene_id": "nope"}))
    assert "error" in out and "known_scenes" in out


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


async def test_toolbox_generate_queues_and_teaches(config, workspace):
    """generate is the one generation tool: valid kinds queue, bad requests
    come back with teaching problems, unwired kinds fail loudly."""
    import json as _json

    from reelstudio.agent.tools import TOOLS, ToolBox
    from reelstudio.app import ReelStudio

    state = ReelStudio(config)
    box = ToolBox(state)

    # the generate tool is derived from the registry, all kinds visible
    gen = next(t for t in TOOLS if t["function"]["name"] == "generate")
    enum = gen["function"]["parameters"]["properties"]["kind"]["enum"]
    assert enum == ["scene", "music", "assemble", "sheet", "still", "image_edit"]
    # every kind is wired — the descriptions come from the registry summaries
    assert "background" in gen["function"]["description"]  # still -> bg
    assert "shots:" in gen["function"]["description"]      # image_edit -> shot

    # upstream-first ordering for a chain render
    out = _json.loads(await box.call(
        "generate", {"kind": "scene", "scene_ids": ["s3_pinkburst", "s1_ramen"]}))
    assert [j["target"] for j in out["queued"]] == ["s1_ramen", "s3_pinkburst"]
    assert all(j["kind"] == "scene" for j in out["queued"])

    out = _json.loads(await box.call(
        "generate", {"kind": "scene", "scene_ids": ["nope"]}))
    assert "error" in out
    assert "s1_ramen" in out["problems"][1]

    # stale: true queues every scene (no manifest yet = all stale)
    out = _json.loads(await box.call("generate", {"kind": "scene", "stale": True}))
    assert len(out["queued"]) == 3

    # missing targets teach what the yaml section that owns them expects
    out = _json.loads(await box.call("generate", {"kind": "still"}))
    assert "locations:" in out["error"] or any(
        "locations:" in p for p in out["problems"])

    out = _json.loads(await box.call("generate", {"kind": "image_edit"}))
    assert "shots:" in out["error"] or any(
        "shots:" in p for p in out["problems"])

    out = _json.loads(await box.call("generate", {"kind": "wat"}))
    assert "known kinds" in out["error"]


async def test_toolbox_read_model_and_assets(config, workspace):
    """get_project is the full read model (stills map included); get_assets
    exposes the derived library with used_by."""
    import json as _json

    from reelstudio.agent.tools import ToolBox
    from reelstudio.app import ReelStudio

    state = ReelStudio(config)
    box = ToolBox(state)

    view = _json.loads(await box.call("get_project", {}))
    assert [s["id"] for s in view["scenes"]] == ["s1_ramen", "s2_bowldrop", "s3_pinkburst"]
    assert all(s["stale"] for s in view["scenes"])
    assert view["stills"] == {"opening": True, "impact": True, "end": True}
    assert view["alias_names"] == ["fox"]

    assets = _json.loads(await box.call("get_assets", {}))
    scenes = assets["groups"]["scenes"]
    opening = next(a for a in scenes if a["labels"] == ["still", "still:opening"])
    assert opening["used_by"] == ["s1_ramen"]


async def test_read_model_is_one_derivation_api_and_tool(config, workspace):
    """The API route and the agent tool must serve the same read model."""
    import json as _json

    from aiohttp.test_utils import TestClient, TestServer

    from reelstudio.agent.tools import ToolBox
    from reelstudio.app import STATE_KEY, ReelStudio, create_app

    app = create_app(config)
    tc = TestClient(TestServer(app))
    await tc.start_server()
    resp = await tc.get("/reelstudio/api/project")
    api_view = await resp.json()
    tool_view = _json.loads(await ToolBox(app[STATE_KEY]).call("get_project", {}))
    assert api_view == tool_view
    await tc.close()


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
