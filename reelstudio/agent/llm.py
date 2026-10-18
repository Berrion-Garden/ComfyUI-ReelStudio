"""Chat agent: an OpenAI-compatible client for the Berrion garden gateway."""

import json

import aiohttp

from ..config import Config

SYSTEM_PROMPT = """You are the Reel Studio agent: you help the user edit and \
regenerate a YAML-driven scene-chain video (reel.yaml).

Each scene has a video description (H3-Context-IR, plain prose directives with \
integrated_multimodal_description), optional negative prompt, a sound_effects \
soundscape (baked into the clip), optional music segment anchor, and optional \
post (freeze). Scenes chain by `next:` slugs; a scene with `first: prev_last` \
anchors on the previous scene's actual last frame — keep junctions frame-exact \
by re-rendering the downstream scene too when an upstream ending changes.

When the user asks for a change: edit the YAML (one atomic update), explain \
what changed in one or two sentences, and offer or start a re-render of only \
the affected scenes. Never render everything when two scenes changed — but \
an edit to the active `style:` block or `styles:` map legitimately restyles \
every scene, so the whole reel going stale there is correct. Shared \
`styles:`/`locations:` blocks are merged into every prompt by the machinery; \
scene descriptions hold only what is specific to the shot. The skills below \
marked "on demand" load with the get_skill tool when a task matches their \
description."""


async def chat(config: Config, messages: list[dict], tools: list[dict]) -> dict:
    """One completion call. Returns the assistant message dict."""
    body = {
        "model": config.agent_model,
        "messages": messages,
        "tools": tools,
        "tool_choice": "auto",
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(
                f"{config.agent_base_url}/chat/completions", json=body,
                timeout=aiohttp.ClientTimeout(total=300)) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise RuntimeError(f"gateway {resp.status}: {text[:300]}")
            data = await resp.json()
    return data["choices"][0]["message"]
