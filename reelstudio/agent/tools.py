"""Agent tools — the exact operations a human has, executed server-side.

get_project / get_assets / get_yaml / update_yaml / generate /
currently_selected / view_image / view_frames / get_studio / get_narrative /
update_narrative / import_assets / update_asset_labels / anchor_still /
adopt_renders / get_provenance / get_skill / get_status.
update_yaml validates before saving and generate validates before queueing —
the agent cannot save a broken chain or queue a bogus job, and every
rejection teaches what would be valid.
"""

import json
from pathlib import Path

import yaml

from .. import generate
from .. import jobs as jobs_mod
from .. import narrative as narrative_mod
from .. import readmodel
from .. import studio as studio_mod
from ..assets import asset_file
from ..errors import ReelStudioError
from .skills import load_skills

VIDEO_EXTS = {".mp4", ".webm", ".mov", ".mkv"}

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
                       "scene:/cond: tags), used_by scenes. Their PICTURES "
                       "are delivered to you right after this result — you "
                       "will see them; look before commenting on visuals. "
                       "When the operator says 'this one' or pastes an "
                       "`asset:<path>` reference (from an asset's "
                       "copy-reference menu), call this or match the path "
                       "against get_assets — never guess filenames.",
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
        "name": "anchor_still",
        "description": "The operator's pick flow in one call: make an image "
                       "a scene's start or end. Tags the chosen file "
                       "`still:<name>` in assets.yaml — the label is the "
                       "single owner of 'which option was picked' — sets "
                       "video.first/last to `still:<name>`, and removes any "
                       "legacy `stills:` path entry for that name. Never "
                       "hand-edit `stills:` entries in update_yaml: the yaml "
                       "never grows absolute paths. Pass the asset's "
                       "`asset:<path>` path.",
        "parameters": {"type": "object",
                       "properties": {
                           "path": {"type": "string"},
                           "scene_id": {"type": "string"},
                           "anchor": {"type": "string",
                                      "enum": ["first", "last"],
                                      "description": "the scene's start or "
                                                     "end"},
                           "name": {"type": "string",
                                    "description": "the anchor slug; "
                                                   "defaults to the file's "
                                                   "slug"}},
                       "required": ["path", "scene_id", "anchor"]}}},
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
        "name": "view_image",
        "description": "LOOK at an image — you are visual. The file is "
                       "delivered to you as a picture on the next turn. Look "
                       "before judging anything visual: check what a "
                       "generated still actually shows, verify a pick matches "
                       "its description, compare candidates, inspect a "
                       "reference the operator uploaded. One image per call.",
        "parameters": {"type": "object",
                       "properties": {"path": {"type": "string"}},
                       "required": ["path"]}}},
    {"type": "function", "function": {
        "name": "view_frames",
        "description": "LOOK at frames of a rendered video — you are visual. "
                       "Extracts frames at the given seconds (default: six "
                       "evenly spaced) and delivers them as pictures on the "
                       "next turn. Use it to judge motion and flow: how a "
                       "segment opens against its first anchor, how it lands "
                       "on its last, whether a chain of segments reads "
                       "continuously or jumps. One video per call, max 8 "
                       "frames.",
        "parameters": {"type": "object",
                       "properties": {"path": {"type": "string"},
                                      "at": {"type": "array",
                                             "items": {"type": "number"},
                                             "description": "seconds into "
                                                            "the video"}},
                       "required": ["path"]}}},
    {"type": "function", "function": {
        "name": "get_studio",
        "description": "The scene registry: every scene in the studio (with "
                       "its character/location pools) and the current one. "
                       "Read before cross-scene work (imports, references, "
                       "comparisons).",
        "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {
        "name": "get_narrative",
        "description": "The production narrative (storyboard.yaml at the "
                       "studio root): style, ordered acts (each with its "
                       "music/sync notes) and their checkpoints — the "
                       "checkpoint-by-checkpoint story the whole production "
                       "derives from. Read it before and after every edit.",
        "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {
        "name": "update_narrative",
        "description": "Replace the whole narrative with new text (raw YAML "
                       "of {style, acts}). Validated first; the whole update "
                       "is rejected on any structural error. Schema: `style` "
                       "(str) + `acts`, each a mapping {title, music? "
                       "(sync note), checkpoints} where each checkpoint is a "
                       "SCENE {title, characters? (slugs), locations? "
                       "(slugs), shots} and each shot {title, text} is one "
                       "of the script's Prompt N.M beats. Read get_narrative "
                       "first, edit, then submit the complete document. When "
                       "the operator pastes a prompt or an image, work the "
                       "new material into the narrative here — and draft the "
                       "matching character/location YAML with update_yaml.",
        "parameters": {"type": "object",
                       "properties": {"text": {"type": "string"}},
                       "required": ["text"]}}},
    {"type": "function", "function": {
        "name": "import_assets",
        "description": "Copy a character or location pool from another "
                       "scene into the CURRENT one — into a new pool, or "
                       "merged into an existing one with `as` (single-pool "
                       "imports). Never clobbers files; declared labels "
                       "come along (scene:* foreign keys stripped).",
        "parameters": {"type": "object",
                       "properties": {
                           "from": {"type": "string",
                                    "description": "source scene slug"},
                           "characters": {"type": "array",
                                          "items": {"type": "string"}},
                           "backgrounds": {"type": "array",
                                           "items": {"type": "string"}},
                           "as": {"type": "string",
                                  "description": "target pool name "
                                                 "(single-pool imports)"}},
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
        # view_image calls waiting for the loop to deliver their pictures
        self.image_requests: list[str] = []

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
        index. The last one is the primary (what the stage shows). The
        picked images are delivered as pictures right after this result:
        referencing the selection IS looking at it."""
        from ..agent import vision

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
        # the selection's pictures follow this result (primary first, capped)
        image_exts = tuple(vision.IMAGE_EXTS)
        for sel in reversed(picked):
            if len(self.image_requests) >= 6:
                break
            path = str(sel.get("path", ""))
            if path.lower().endswith(image_exts) and \
                    path not in self.image_requests:
                self.image_requests.append(path)
        delivered = len(self.image_requests)
        primary = picked[-1] if picked else None
        return json.dumps(
            {"selected": picked, "primary": primary,
             "count": len(picked),
             "images_following": delivered,
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

    async def _get_narrative(self, _):
        root = studio_mod.resolve(self.state.config.workspace).root
        return json.dumps(narrative_mod.view(root), ensure_ascii=False)

    async def _update_narrative(self, args):
        text = args.get("text")
        if not isinstance(text, str):
            return json.dumps({"error": "text required"})
        try:
            doc = yaml.safe_load(text)
        except yaml.YAMLError as e:
            return json.dumps({"error": f"yaml error: {e}"})
        if not isinstance(doc, dict):
            return json.dumps({"error": "narrative must be a mapping"})
        root = studio_mod.resolve(self.state.config.workspace).root
        narrative_mod.save(root, doc)
        return json.dumps({"saved": True, "path": str(narrative_mod.path(root))})

    async def _import_assets(self, args):
        out = studio_mod.import_assets(
            self.state.config.workspace, str(args.get("from", "")),
            args.get("characters") or (), args.get("backgrounds") or (),
            args.get("as"))
        return json.dumps(out, ensure_ascii=False)

    async def _get_provenance(self, args):
        path = str(args.get("path", ""))
        if path.startswith("asset:"):
            path = path[len("asset:"):]
        return json.dumps(
            jobs_mod.provenance(self.state.config, path), ensure_ascii=False)

    async def _view_image(self, args):
        """The agent's eyes: resolve the path now, and hand it to the loop —
        the picture itself goes out as a user turn (the gateway flattens
        tool results to text)."""
        from ..agent import vision

        path = str(args.get("path", ""))
        if path.startswith("asset:"):
            path = path[len("asset:"):]
        project = self.state.project()
        roots = [self.state.config.workspace,
                 project.meta["still_dir"], project.meta["reel_dir"]]
        label, _ = vision.data_url(path, roots)
        self.image_requests.append(path)
        return json.dumps({"viewing": label,
                           "note": "the image is delivered with the next "
                                   "message — describe what you actually see"})

    async def _view_frames(self, args):
        """The agent's eyes on rendered video: ffmpeg-extract frames into
        the reel dir and deliver them through the same user-turn path as
        view_image — the loop can finally judge the motion it produced."""
        import subprocess

        path = str(args.get("path", ""))
        if path.startswith("asset:"):
            path = path[len("asset:"):]
        project = self.state.project()
        roots = [self.state.config.workspace,
                 project.meta["still_dir"], project.meta["reel_dir"]]
        p = asset_file(path, roots)
        if p.suffix.lower() not in VIDEO_EXTS:
            return json.dumps({"error": f"{p.name} is not a viewable video",
                               "viewable": sorted(VIDEO_EXTS)})
        times = [float(t) for t in (args.get("at") or [])][:8]
        if not times:
            dur = float(subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "csv=p=0", str(p)],
                check=True, capture_output=True, text=True).stdout.strip())
            times = [round(dur * (i + 0.5) / 6, 2) for i in range(6)]
        outdir = Path(project.meta["reel_dir"]) / "_frames"
        outdir.mkdir(parents=True, exist_ok=True)
        frames = []
        for t in times:
            out = outdir / f"{p.stem}_t{t:07.2f}.png"
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", str(t),
                            "-i", str(p), "-frames:v", "1", str(out)],
                           check=True)
            self.image_requests.append(str(out))
            frames.append(out.name)
        return json.dumps({"viewing": frames,
                           "note": f"{len(frames)} frame(s) delivered with "
                                   "the next message — judge the motion and "
                                   "the joints, not just the stills"})

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

    async def _anchor_still(self, args):
        """The operator's pick flow: the chosen image becomes the scene's
        start/end. The `still:<name>` label moves to the chosen file (the
        label is the pick), video.first/last is wired, and any legacy
        `stills:` path entry for that name goes — labels, not paths."""
        from .. import assets as assets_mod
        from .. import project as project_mod

        path = str(args.get("path", ""))
        if path.startswith("asset:"):
            path = path[len("asset:"):]
        scene_id = str(args.get("scene_id", ""))
        anchor = str(args.get("anchor", ""))
        if anchor not in ("first", "last"):
            return json.dumps({"error": "anchor must be 'first' or 'last'"})
        if not scene_id:
            return json.dumps({"error": "scene_id required"})
        project = self.state.project()
        if project.scene(scene_id) is None:
            return json.dumps({
                "error": f"unknown scene {scene_id!r}",
                "known_scenes": [s["id"] for s in project.scenes]})
        p = assets_mod.asset_file(path, [self.state.config.workspace,
                                         project.meta["still_dir"],
                                         project.meta["reel_dir"]])
        if not p.is_file():
            return json.dumps({"error": f"no such asset: {p}"})
        name = str(args.get("name") or p.stem.rstrip("_") or p.stem)
        picked = assets_mod.pick_still(
            self.state.config.workspace, project.meta["still_dir"],
            str(p), name)
        wired = project_mod.anchor_still(
            self.state.config, scene_id, anchor, name)
        return json.dumps({**wired, "picked": picked}, ensure_ascii=False)

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
