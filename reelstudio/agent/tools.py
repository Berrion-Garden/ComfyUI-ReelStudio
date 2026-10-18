"""Agent tools — the exact operations a human has, executed server-side.

get_project / get_assets / get_yaml / update_yaml / generate / get_status.
update_yaml validates before saving and generate validates before queueing —
the agent cannot save a broken chain or queue a bogus job, and every rejection
teaches what would be valid.
"""

import json

from .. import generate
from .. import readmodel
from ..errors import ReelStudioError

TOOLS = [
    {"type": "function", "function": {
        "name": "get_project",
        "description": "The read model: per-scene staleness/rendered/anchors/"
                       "start times, music segments, overlays, the stills map "
                       "(present or missing), alias names, flags. Read it "
                       "before and after every edit.",
        "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {
        "name": "get_assets",
        "description": "The derived asset library: character pose pools, "
                       "custom images, themes, audio, and which scenes use "
                       "each still (used_by). Use it to find anchor images "
                       "by label instead of guessing filenames.",
        "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {
        "name": "get_yaml",
        "description": "Read the raw reel.yaml text.",
        "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {
        "name": "update_yaml",
        "description": "Replace the whole reel.yaml with new text. Validated "
                       "first; the whole update is rejected on any validation "
                       "error. Read get_yaml first, edit, then submit the "
                       "complete file.",
        "parameters": {"type": "object",
                       "properties": {"text": {"type": "string"}},
                       "required": ["text"]}}},
    generate.tool(),
    {"type": "function", "function": {
        "name": "get_status",
        "description": "Current queued/running/done/error jobs.",
        "parameters": {"type": "object", "properties": {}, "required": []}}},
]


class ToolBox:
    def __init__(self, state):
        self.state = state  # reelstudio.app.ReelStudio

    async def call(self, name: str, args: dict) -> str:
        handler = getattr(self, f"_{name}", None)
        if handler is None:
            return json.dumps({"error": f"unknown tool {name!r}",
                               "known_tools": [t["function"]["name"] for t in TOOLS]})
        try:
            return await handler(args)
        except ReelStudioError as e:
            return json.dumps({"error": str(e),
                               "problems": getattr(e, "problems", None)})
        except Exception as e:  # noqa: BLE001 - surfaced to the agent
            return json.dumps({"error": f"{type(e).__name__}: {e}"})

    async def _get_project(self, _):
        return json.dumps(readmodel.project_view(self.state), ensure_ascii=False)

    async def _get_assets(self, _):
        return json.dumps(readmodel.asset_view(self.state), ensure_ascii=False)

    async def _get_yaml(self, _):
        return self.state.config.yaml_path.read_text()

    async def _update_yaml(self, args):
        text = args.get("text")
        if not isinstance(text, str):
            return json.dumps({"error": "text required"})
        warnings = self.state.project().save(text)
        return json.dumps({"saved": True, "warnings": warnings})

    async def _generate(self, args):
        project = self.state.project()
        specs = generate.plan(project, args.get("kind"), args)
        jobs = [self.state.enqueue(kind, target) for kind, target in specs]
        return json.dumps({"queued": [j.view() for j in jobs]})

    async def _get_status(self, _):
        return json.dumps({"jobs": [j.view() for j in self.state.jobs.values()]})
