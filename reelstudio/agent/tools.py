"""Agent tools — the exact operations a human has, executed server-side.

get_project / get_assets / get_yaml / update_yaml / generate / get_skill /
get_status. update_yaml validates before saving and generate validates
before queueing — the agent cannot save a broken chain or queue a bogus
job, and every rejection teaches what would be valid.
"""

import json

from .. import generate
from .. import readmodel
from .. import studio as studio_mod
from ..errors import ReelStudioError
from .skills import load_skills

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
        "name": "currently_selected",
        "description": "The asset the operator is currently looking at in the "
                       "studio (the one highlighted in the asset browser): "
                       "slug, path, group, labels (char:/scene:/cond: tags), "
                       "used_by scenes. When the operator says 'this one' or "
                       "'the selected asset', call this instead of guessing.",
        "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {
        "name": "get_studio",
        "description": "The scene registry: every scene in the studio, the "
                       "current one, and each scene's characters/backgrounds. "
                       "Read before cross-scene work (imports, references).",
        "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {
        "name": "import_assets",
        "description": "Import character pools and background plates from "
                       "another scene into the CURRENT one (copies files + "
                       "labels, scene: foreign keys stripped). Name "
                       "collisions are refused.",
        "parameters": {"type": "object",
                       "properties": {
                           "from": {"type": "string",
                                    "description": "source scene slug"},
                           "characters": {"type": "array",
                                          "items": {"type": "string"}},
                           "backgrounds": {"type": "array",
                                           "items": {"type": "string"}}},
                       "required": ["from"]}}},
    {"type": "function", "function": {
        "name": "get_skill",
        "description": "Load an on-demand skill's full body by name. The "
                       "system prompt's 'Skills on demand' index lists the "
                       "names and what each covers; call this when your "
                       "current task matches one.",
        "parameters": {"type": "object",
                       "properties": {"name": {"type": "string"}},
                       "required": ["name"]}}},
    {"type": "function", "function": {
        "name": "get_status",
        "description": "Current queued/running/done/error jobs.",
        "parameters": {"type": "object", "properties": {}, "required": []}}},
]


class ToolBox:
    def __init__(self, state, selected: dict | None = None):
        self.state = state  # reelstudio.app.ReelStudio
        self.selected = selected  # the operator's current asset selection

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

    async def _currently_selected(self, _) -> str:
        """The request-scoped selection, with labels refreshed from the
        index (the FE's copy can be stale after an edit)."""
        if not self.selected:
            return json.dumps({"selected": None,
                               "hint": "nothing is selected in the studio — "
                                       "ask the operator to click an asset"})
        index = readmodel.asset_view(self.state)
        path = str(self.selected.get("path", ""))
        fresh = next((a for items in index["groups"].values() for a in items
                      if a["path"] == path), None)
        return json.dumps({"selected": {**self.selected,
                                        "labels": (fresh or {}).get(
                                            "labels", self.selected.get("labels", [])),
                                        "used_by": (fresh or {}).get(
                                            "used_by", [])}},
                          ensure_ascii=False)

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

    async def _get_studio(self, _):
        return json.dumps(
            studio_mod.view_of(self.state.config.workspace), ensure_ascii=False)

    async def _import_assets(self, args):
        result = studio_mod.import_assets(
            self.state.config.workspace, str(args.get("from", "")),
            args.get("characters") or [], args.get("backgrounds") or [])
        return json.dumps(result, ensure_ascii=False)

    async def _get_skill(self, args):
        name = args.get("name")
        skills = load_skills()
        for skill in skills:
            if skill["name"] == name:
                return skill["body"]
        return json.dumps({"error": f"unknown skill {name!r}",
                           "known_skills": [s["name"] for s in skills]})

    async def _get_status(self, _):
        return json.dumps({"jobs": [j.view() for j in self.state.jobs.values()]})
