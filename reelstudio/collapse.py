"""The collapse: what a scene will ACTUALLY be rendered from.

reel.py (the single pipeline implementation) merges the yaml's shared look
blocks, aliases and scene layers into the final generation input — prompt
text, negative, resolved anchors with file content hashes. A `collapse`
subcommand emits that per scene as JSON, deterministic given
(reel.yaml, reel.py, still files) and no GPU.

The studio caches that artifact and compares it against the one recorded in
the manifest at render time: cached != fresh means the scene changed, in a
deterministic, code-driven way. One staleness mechanism instead of hashes
plus junction heuristics — the collapse carries the resolved upstream anchor
hash, so a re-rendered upstream invalidates its dependents automatically.
"""

import json

from . import reel as reel_pipeline
from .project import Config, Project, file_hash


def cache_key(project: Project) -> str:
    """What the collapse depends on: the yaml, the pipeline script, the stills
    — and the recorded deliverables, since a resolved prev_last anchor hashes
    the upstream's current deliverable. The manifest changes exactly when a
    render/adopt records, so it is the right drift signal for that part."""
    from . import manifest as manifest_mod

    deliverables = {sid: (e.get("video") or {}).get("path", {}).get("file")
                    for sid, e
                    in manifest_mod.load(project.meta["reel_dir"])
                    .get("scenes", {}).items()}
    parts = [file_hash(project.config.yaml_path),
             file_hash(project.config.workspace / "reel.py")]
    parts += [f"{name}:{file_hash(project.still_path(name) or '')}"
              for name in sorted(project.still_names())]
    parts.append(json.dumps(deliverables, sort_keys=True))
    return ":".join(parts)


def cache_path(config: Config):
    return config.work_dir / "collapse.json"


def fresh(project: Project) -> dict | None:
    """Run `reel.py collapse`; {"scenes": {id: <generation input>}}, or None
    when the workspace's reel.py predates the subcommand."""
    try:
        out = reel_pipeline.run_sync(project.config.workspace, "collapse")
        data = json.loads(out[out.index("{"):])
        return data.get("scenes") or None
    except (ValueError, FileNotFoundError, reel_pipeline.ReelScriptError):
        return None


def current(project: Project) -> dict | None:
    """The fresh collapse, cached in .work keyed on its inputs. None means
    'workspace cannot collapse' — callers fall back to hash staleness."""
    cp = cache_path(project.config)
    key = cache_key(project)
    try:
        data = json.loads(cp.read_text())
        if data.get("key") == key:
            return data.get("scenes") or None
    except (OSError, ValueError):
        pass
    scenes = fresh(project)
    if scenes is None:
        return None
    cp.parent.mkdir(parents=True, exist_ok=True)
    cp.write_text(json.dumps({"key": key, "scenes": scenes}, sort_keys=True))
    return scenes
