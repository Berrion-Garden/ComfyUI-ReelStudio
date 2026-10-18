"""The project read model — one derivation shared by the HTTP API and the
agent's get_project tool.

This is the single copy of "what does the timeline look like right now":
scene state (staleness, deliverables, anchors, times), music segments and
overlays, the stills map, aliases and flags. The API route adds nothing but
a JSON envelope; the agent tool adds nothing at all.
"""

from pathlib import Path

from . import assets as assets_mod
from . import audio as audio_mod
from . import manifest as manifest_mod
from . import timeline
from .audio import music_segments


def project_view(state, api: str = "/reelstudio/api") -> dict:
    project = state.project()
    reel_dir = project.meta["reel_dir"]
    manifest = manifest_mod.load(reel_dir)
    stale = set(timeline.stale_scenes(project, manifest, reel_dir))
    starts = timeline.scene_starts(project)

    scenes = []
    for i, s in enumerate(project.scenes):
        view = timeline.scene_view(project, s["id"])
        entry = manifest["scenes"].get(s["id"], {})
        video_file = (entry.get("video") or {}).get("path", {}).get("file")
        view["video_url"] = (f"{api}/scene/{s['id']}/artifact/video"
                             if video_file else None)
        view["rendered"] = bool(video_file)
        view["stale"] = s["id"] in stale
        view["start_s"] = starts[i]
        scenes.append(view)

    music = []
    for m in music_segments(project):
        rendered = manifest_mod.music_file(reel_dir, m["name"])
        music.append({
            "name": m["name"], "start_s": m["start"], "duration_s": m["dur"],
            "gain": m["gain"],
            "stale": (manifest.get("music", {}).get(m["name"], {}).get("hash")
                      != m["hash"]),
            "present": rendered is not None,
            "url": f"{api}/music/{m['name']}/artifact" if rendered else None,
        })

    # the real audio tracks (`audio:`) — what the production mix actually uses
    overlays = []
    for m in audio_mod.audio_tracks(project):
        p = Path(m["file"]).expanduser()
        overlays.append({
            "index": m["index"], "name": m["name"],
            "start_s": m["start"], "duration_s": m["dur"],
            "gain": m["gain"], "seek": m["seek"], "fades": m["fades"],
            "present": p.is_file(),
            "url": (f"{api}/audio/{m['index']}/artifact" if p.is_file()
                    else None),
        })

    # referenced stills: `present: false` is the "unknown still ref on disk"
    # signal the agent can act on
    stills = {}
    for name in project.stills:
        p = project.still_path(name)
        stills[name] = p is not None and p.exists()

    return {
        "yaml_path": str(state.config.yaml_path),
        "fps": project.fps,
        "width": project.meta.get("width"),
        "height": project.meta.get("height"),
        "total_s": timeline.total_dur(project),
        "final_path": project.meta.get("final"),
        "flags": project.raw.get("flags", {}),
        "sfx_volume": project.raw.get("sfx_volume") or [],
        "alias_names": list(project.aliases),
        "stills": stills,
        "scenes": scenes,
        "music": music,
        "overlays": overlays,
        "final_url": (f"{api}/final"
                      if Path(project.meta.get("final", "")).exists() else None),
        "jobs": [j.view() for j in state.jobs.values()],
    }


def asset_view(state) -> dict:
    """The derived asset library, for the agent's get_assets tool. No URLs —
    the agent works with slugs, labels and workspace paths."""
    return assets_mod.index_assets(state.config.workspace, state.project())
