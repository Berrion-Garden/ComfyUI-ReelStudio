"""Agentic loop: gateway <-> tools, streamed to the UI as SSE events.

Event shapes: {"type": "message", "text": ...} | {"type": "tool_call", ...} |
{"type": "tool_result", ...} | {"type": "error", ...} | {"type": "done"}.
"""

import json

from .llm import SYSTEM_PROMPT, chat
from .tools import TOOLS, ToolBox

MAX_ITERATIONS = 8


async def run(config, history: list[dict], toolbox: ToolBox):
    """Yield SSE-able dicts for one user turn. `history` is the conversation
    so far (without the system prompt); it is copied, never mutated — the
    caller rebuilds its history from the yielded events."""
    history = list(history)
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, *history]
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
