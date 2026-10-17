"""Agent tools: the exact operations a human has, executed server-side.

get_project / get_yaml / update_yaml / render_scenes / assemble / get_status.
update_yaml validates before saving — the agent cannot save a broken chain.
"""

import json

from .. import manifest as manifest_mod
from .. import timeline
from ..assemble import music_segments
from ..errors import ReelStudioError

TOOLS = [
    {"type": "function", "function": {
        "name": "get_project",
        "description": "Get the full timeline state: scenes, anchors, artifacts, staleness.",
        "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {
        "name": "get_yaml",
        "description": "Read the raw reel.yaml text.",
        "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {
        "name": "update_yaml",
        "description": "Replace the whole reel.yaml with new text. Validated first; "
                       "the whole update is rejected on any validation error. "
                       "Read get_yaml first, edit, then submit the complete file.",
        "parameters": {"type": "object",
                       "properties": {"text": {"type": "string"}},
                       "required": ["text"]}}},
    {"type": "function", "function": {
        "name": "render_scenes",
        "description": "Queue H3 renders. Pass scene_ids, or {stale: true} for every "
                       "stale scene (changed config or re-rendered prev_last upstream).",
        "parameters": {"type": "object",
                       "properties": {
                           "scene_ids": {"type": "array", "items": {"type": "string"}},
                           "stale": {"type": "boolean"}},
                       "required": []}}},
    {"type": "function", "function": {
        "name": "render_music",
        "description": "Regenerate one anchored music segment by name.",
        "parameters": {"type": "object",
                       "properties": {"name": {"type": "string"}},
                       "required": ["name"]}}},
    {"type": "function", "function": {
        "name": "assemble",
        "description": "Final production: music bed + bell + concat + mix.",
        "parameters": {"type": "object",
                       "properties": {"use_music": {"type": "boolean"}},
                       "required": []}}},
    {"type": "function", "function": {
        "name": "get_status",
        "description": "Current render/assemble job statuses.",
        "parameters": {"type": "object", "properties": {}, "required": []}}},
]


class ToolBox:
    def __init__(self, state):
        self.state = state  # reelstudio.app.ReelStudio

    async def call(self, name: str, args: dict) -> str:
        handler = getattr(self, f"_{name}", None)
        if handler is None:
            return json.dumps({"error": f"unknown tool {name!r}"})
        try:
            return await handler(args)
        except ReelStudioError as e:
            return json.dumps({"error": str(e),
                               "problems": getattr(e, "problems", None)})
        except Exception as e:  # noqa: BLE001 - surfaced to the agent
            return json.dumps({"error": f"{type(e).__name__}: {e}"})

    async def _get_project(self, _):
        project = self.state.project()
        manifest = manifest_mod.load(project.meta["reel_dir"])
        stale = set(timeline.stale_scenes(project, manifest,
                                          project.meta["reel_dir"]))
        starts = timeline.scene_starts(project)
        scenes = []
        for i, s in enumerate(project.scenes):
            v = timeline.scene_view(project, s["id"])
            entry = manifest["scenes"].get(s["id"], {})
            v["stale"] = s["id"] in stale
            v["start_s"] = starts[i]
            v["rendered"] = bool((entry.get("video") or {}).get("path", {}).get("file"))
            scenes.append(v)
        return json.dumps({
            "total_s": timeline.total_dur(project),
            "fps": project.fps,
            "scenes": scenes,
            "music": [{"name": m["name"], "start_s": m["start"],
                       "duration_s": m["dur"]} for m in music_segments(project)],
        }, ensure_ascii=False)

    async def _get_yaml(self, _):
        return self.state.config.yaml_path.read_text()

    async def _update_yaml(self, args):
        text = args.get("text")
        if not isinstance(text, str):
            return json.dumps({"error": "text required"})
        project = self.state.project()
        project.save(text)
        return json.dumps({"saved": True})

    async def _render_scenes(self, args):
        project = self.state.project()
        if args.get("stale"):
            manifest = manifest_mod.load(project.meta["reel_dir"])
            wanted = timeline.stale_scenes(project, manifest,
                                           project.meta["reel_dir"])
        else:
            wanted = args.get("scene_ids") or []
        if not wanted:
            return json.dumps({"error": "nothing to render (no scene_ids, none stale)"})
        known = project.by_id()
        unknown = [s for s in wanted if s not in known]
        if unknown:
            return json.dumps({"error": f"unknown scenes: {unknown}"})
        order = [s["id"] for s in project.scenes]
        jobs = [self.state.enqueue("scene", sid)
                for sid in sorted(wanted, key=order.index)]
        return json.dumps({"queued": [j.view() for j in jobs]})

    async def _render_music(self, args):
        name = args.get("name")
        job = self.state.enqueue("music", name or "")
        return json.dumps({"queued": [job.view()]})

    async def _assemble(self, args):
        flags = self.state.project().raw.get("flags", {})
        use_music = bool(args.get("use_music", not flags.get("skip_music", True)))
        job = self.state.enqueue("assemble", "music" if use_music else "no-music")
        return json.dumps({"queued": [job.view()]})

    async def _get_status(self, _):
        return json.dumps({"jobs": [j.view() for j in self.state.jobs.values()]})
