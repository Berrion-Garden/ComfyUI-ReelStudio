"""Agentic loop: gateway <-> tools, streamed to the UI as SSE events.

Event shapes: {"type": "message", "text": ...} | {"type": "tool_call", ...} |
{"type": "tool_result", ...} | {"type": "error", ...} | {"type": "done"}.
"""

import json

from .llm import SYSTEM_PROMPT, chat
from .skills import system_prompt
from .tools import TOOLS, ToolBox

MAX_ITERATIONS = 8


async def run(config, history: list[dict], toolbox: ToolBox,
              images: list[str] | None = None):
    """Yield SSE-able dicts for one user turn. `history` is the conversation
    so far INCLUDING the user's new message (text-only); `images` are asset
    paths delivered as pictures beside it — the operator's primary selection.
    The history is copied, never mutated — the caller rebuilds its history
    from the yielded events."""
    from . import vision

    history = list(history)
    roots = None
    try:
        project = toolbox.state.project()
        roots = [toolbox.state.config.workspace,
                 project.meta["still_dir"], project.meta["reel_dir"]]
    except Exception:  # noqa: BLE001 - a broken yaml must not blind the agent
        pass
    shown: list[tuple[str, str]] = []
    for path in images or []:
        try:
            shown.append(vision.data_url(path, roots))
        except Exception:  # noqa: BLE001 - a bad attachment must not kill the turn
            pass

    messages = [{"role": "system", "content": system_prompt(SYSTEM_PROMPT)}]
    if history and history[-1].get("role") == "user" \
            and isinstance(history[-1].get("content"), str):
        *rest, last = history
        messages += [*rest, vision.content_parts(last["content"], shown)]
    else:
        messages += history

    for _ in range(MAX_ITERATIONS):
        message = await chat(config, messages, TOOLS)
        messages.append(message)

        for call in message.get("tool_calls") or []:
            name = call["function"]["name"]
            args = json.loads(call["function"]["arguments"] or "{}")
            yield {"type": "tool_call", "name": name, "args": args}
            result = await toolbox.call(name, args)
            yield {"type": "tool_result", "name": name, "result": result}
            messages.append({"role": "tool", "tool_call_id": call["id"],
                             "content": result})

        # view_image deliveries: the pictures ride a user turn (the gateway
        # flattens tool results to text-only)
        if toolbox.image_requests:
            pending, toolbox.image_requests = toolbox.image_requests, []
            shots: list[tuple[str, str]] = []
            for path in pending:
                try:
                    shots.append(vision.data_url(path, roots))
                except Exception:  # noqa: BLE001 - a bad path must not kill the turn
                    pass
            if shots:
                labels = ", ".join(label for label, _ in shots)
                messages.append(vision.content_parts(
                    f"the image(s) you requested: {labels}", shots))

        text = message.get("content")
        if text:
            yield {"type": "message", "text": text}
        if not message.get("tool_calls"):
            history.extend(messages[1:])
            yield {"type": "done"}
            return

    history.extend(messages[1:])
    yield {"type": "message", "text": "(stopped after many tool rounds — ask me to continue)"}
    yield {"type": "done"}
