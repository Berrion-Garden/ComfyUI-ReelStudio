"""Skill loading and agent injection."""


def test_all_skills_load_with_frontmatter():
    from reelstudio.agent.skills import load_skills

    skills = load_skills()
    names = {s["name"] for s in skills}
    assert {"reel-yaml-schema", "h3-prompting", "junction-doctrine",
            "agent-workflow", "app-troubleshooting"} <= names
    for s in skills:
        assert s["description"], f"{s['name']} needs a description"
        assert len(s["body"]) > 200, f"{s['name']} body too thin"


def test_system_prompt_injects_all_skills():
    from reelstudio.agent.llm import SYSTEM_PROMPT
    from reelstudio.agent.skills import system_prompt

    prompt = system_prompt(SYSTEM_PROMPT)
    assert prompt.startswith("You are the Reel Studio agent")
    for marker in (
            "NEVER show the landing",             # junction-doctrine
            "integrated_multimodal_description",  # h3-prompting
            "update_yaml",                        # agent-workflow
            "17n+5",                              # schema
            "reel.py"):                           # app-troubleshooting
        assert marker in prompt, f"missing: {marker}"


def test_missing_explicit_skills_dir_is_an_error(tmp_path):
    import pytest

    from reelstudio.agent.skills import system_prompt
    from reelstudio.errors import ReelStudioError

    with pytest.raises(ReelStudioError):
        system_prompt("base", dir_path=tmp_path)


def test_env_override(tmp_path, monkeypatch):
    (tmp_path / "tiny.md").write_text(
        "---\nname: tiny\ndescription: a tiny test skill\n---\nBody here.")
    monkeypatch.setenv("REELSTUDIO_SKILLS_DIR", str(tmp_path))
    from reelstudio.agent.skills import load_skills

    assert [s["name"] for s in load_skills()] == ["tiny"]


async def test_agent_receives_skills_in_system_message(config, workspace):
    """The gateway sees the system prompt WITH the skills injected."""
    from dataclasses import replace

    from aiohttp.test_utils import TestClient, TestServer

    from reelstudio.agent.loop import run
    from reelstudio.agent.tools import ToolBox
    from reelstudio.app import ReelStudio

    captured = []

    def gateway_app():
        from aiohttp import web

        async def completions(request: web.Request) -> web.Response:
            body = await request.json()
            captured.append(body)
            return web.json_response({"choices": [{"message": {
                "role": "assistant", "content": "ok", "tool_calls": None}}]})

        app = web.Application()
        app.router.add_post("/v1/chat/completions", completions)
        return app

    server = TestServer(gateway_app(), host="127.0.0.1", port=8288)
    await server.start_server()
    state = ReelStudio(replace(config, agent_base_url="http://127.0.0.1:8288/v1"))
    _ = [e async for e in run(state.config, [], ToolBox(state))]

    system = captured[0]["messages"][0]
    assert system["role"] == "system"
    assert "junction-doctrine" in system["content"] or \
        "NEVER show the landing" in system["content"]
    assert "You are the Reel Studio agent" in system["content"]
    await server.close()
