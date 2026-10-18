"""Agent tools — the exact operations a human has, executed server-side.

get_project / get_assets / get_yaml / update_yaml / generate /
currently_selected / get_studio / import_assets / update_asset_labels /
adopt_renders / get_provenance / get_skill / get_status. update_yaml
validates before saving and generate validates before queueing — the agent
cannot save a broken chain or queue a bogus job, and every rejection teaches
what would be valid.
"""

import json
from pathlib import Path

from .. import generate
from .. import jobs as jobs_mod
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
        "description": "The asset(s) the operator is currently looking at in "
                       "the studio — every picked one (shift-click "
                       "multi-selects), the last being the primary shown on "
                       "the stage. Each: slug, path, group, labels (char:/"
                       "scene:/cond: tags), used_by scenes. When the operator "
                       "says 'this one' or pastes an `asset:<path>` reference "
                       "(from an asset's copy-reference menu), call this or "
                       "match the path against get_assets — never guess "
                       "filenames.",
        "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {
        "name": "update_asset_labels",
        "description": "Add or remove labels on one library asset in "
                       "assets.yaml — tag a pick `ref` (the tag char_ref/"
                       "plate_ref resolve: what the next generation "
                       "references), remove `non-verified` to keep a "
                       "generated image, add `cond:`/`shot:` context tags. "
                       "Read get_assets first; pass the asset's `asset:<path>`"
                       " path. Derived labels (char:, scene:, used_by) come "
                       "from the pipeline and cannot be edited here.",
        "parameters": {"type": "object",
                       "properties": {
                           "path": {"type": "string"},
                           "add": {"type": "array", "items": {"type": "string"},
                                   "description": "labels to add"},
                           "remove": {"type": "array", "items": {"type": "string"},
                                      "description": "labels to remove"}},
                       "required": ["path"]}}},
    {"type": "function", "function": {
        "name": "adopt_renders",
        "description": "Declare the CURRENT deliverables current so staleness "
                       "starts from truth — the manifest records each "
                       "existing render against the present config. Only on "
                       "explicit operator instruction (their ✓ adopt on the "
                       "timeline does one scene); pass scene_id to narrow it.",
        "parameters": {"type": "object",
                       "properties": {"scene_id": {"type": "string",
                                                   "description": "one scene "
                                                                  "only"}},
                       "required": []}}},
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
        "name": "get_provenance",
        "description": "How one generated file was made: its job id, the "
                       "queued request (kind/target/args), the H3 noise seed "
                       "for videos, and — for images — the exact prompt, "
                       "negative prompt, seed, steps and models embedded in "
                       "the PNG. Pass the asset's `asset:<path>` path.",
        "parameters": {"type": "object",
                       "properties": {"path": {"type": "string"}},
                       "required": ["path"]}}},
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
    def __init__(self, state, selected: list[dict] | None = None):
        self.state = state  # reelstudio.app.ReelStudio
        self.selected = selected  # the operator's current selection (ordered)

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
        """The request-scoped selection — every asset the operator has
        picked (shift-click multi-selects), labels refreshed from the
        index. The last one is the primary (what the stage shows)."""
        if not self.selected:
            return json.dumps({"selected": None,
                               "hint": "nothing is selected in the studio — "
                                       "ask the operator to click an asset"})
        index = readmodel.asset_view(self.state)
        fresh_items = [a for items in index["groups"].values() for a in items]
        picked = []
        for sel in self.selected:
            path = str(sel.get("path", ""))
            fresh = next((a for a in fresh_items if a["path"] == path), None)
            picked.append({**sel,
                           "labels": (fresh or {}).get(
                               "labels", sel.get("labels", [])),
                           "used_by": (fresh or {}).get("used_by", [])})
        primary = picked[-1] if picked else None
        return json.dumps(
            {"selected": picked, "primary": primary,
             "count": len(picked),
             "hint": (f"{len(picked)} assets selected; the operator is "
                      f"looking at {primary.get('slug', '')}"
                      if len(picked) > 1 else "")},
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
        jobs = [self.state.enqueue(kind, target, args)
                for kind, target in specs]
        return json.dumps({"queued": [j.view() for j in jobs]})

    async def _get_studio(self, _):
        return json.dumps(
            studio_mod.view_of(self.state.config.workspace), ensure_ascii=False)

    async def _import_assets(self, args):
        result = studio_mod.import_assets(
            self.state.config.workspace, str(args.get("from", "")),
            args.get("characters") or [], args.get("backgrounds") or [])
        return json.dumps(result, ensure_ascii=False)

    async def _get_provenance(self, args):
        path = str(args.get("path", ""))
        if path.startswith("asset:"):
            path = path[len("asset:"):]
        return json.dumps(
            jobs_mod.provenance(self.state.config, path), ensure_ascii=False)

    async def _update_asset_labels(self, args):
        """Add/remove declared labels on one asset — the same write the
        operator's tag editor does, minus the derived labels: they come from
        the pipeline and stay pipeline-owned."""
        from .. import assets as assets_mod

        path = str(args.get("path", ""))
        if path.startswith("asset:"):
            path = path[len("asset:"):]
        add = [str(x) for x in (args.get("add") or [])]
        remove = [str(x) for x in (args.get("remove") or [])]
        if not add and not remove:
            return json.dumps({"error": "nothing to do — pass add and/or remove"})
        project = self.state.project()
        still_dir = project.meta["still_dir"]
        p = assets_mod.asset_file(path, [self.state.config.workspace, still_dir])
        rel = assets_mod._rel(p, [self.state.config.workspace, Path(still_dir)])
        declared = assets_mod._labels_file(self.state.config.workspace).get(rel, [])
        labels = [l for l in dict.fromkeys(declared + add) if l not in remove]
        result = assets_mod.set_labels(
            self.state.config.workspace, still_dir, path, labels)
        return json.dumps({"asset": result["asset"],
                           "labels": result["labels"],
                           "added": [l for l in add if l in result["labels"]],
                           "removed": [l for l in remove
                                       if l not in result["labels"]]})

    async def _adopt_renders(self, args):
        from .. import manifest as manifest_mod

        project = self.state.project()
        scene_id = str(args["scene_id"]) if args.get("scene_id") else None
        if scene_id and scene_id not in project.by_id():
            return json.dumps({"error": f"unknown scene {scene_id!r}",
                               "known_scenes": list(project.by_id())})
        adopted = manifest_mod.adopt_existing(
            project.meta["reel_dir"], project, scene_id)
        return json.dumps({"adopted": adopted, "scene_id": scene_id})

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
