"""The collapse: reel.py's merged generation input, cached by the studio and
diffed against the manifest — the one deterministic staleness mechanism."""

import json

from conftest import write_stub_reel


def _project(config):
    from reelstudio.project import load

    return load(config)


def _render_all_and_record(project, config):
    """Run every scene through the workspace reel.py and record deliverables
    exactly like the app does (generation collapse included)."""
    from reelstudio import collapse as collapse_mod
    from reelstudio import generate

    for _, target in generate.plan(project, "scene", {"stale": True}):
        generate.run_job(project, None, str(config.work_dir), "scene", target)


def _stale(project, config):
    from reelstudio import collapse as collapse_mod
    from reelstudio import manifest as manifest_mod
    from reelstudio import timeline

    return timeline.stale_scenes(
        project, manifest_mod.load(project.meta["reel_dir"]),
        project.meta["reel_dir"], collapse=collapse_mod.current(project))


def test_current_collapses_and_caches(config, workspace):
    from reelstudio import collapse as collapse_mod

    project = _project(config)
    scenes = collapse_mod.current(project)
    assert set(scenes) == {"s1_ramen", "s2_bowldrop", "s3_pinkburst"}
    s1 = scenes["s1_ramen"]
    # the merge: style pro + location pro + scene description, aliases resolved
    assert s1["prompt"].startswith("2D anime, cel-shaded")
    assert "university campus plaza at golden sunset" in s1["prompt"]
    assert "the pink fox boy" in s1["prompt"]
    # cons merged, deduped (scene negative overlaps the style con)
    assert s1["negative"].count("watermark") == 1
    assert "rain" in s1["negative"]

    # a second call serves the cache, and it is invalidated when the yaml moves
    cache = collapse_mod.cache_path(config)
    first = json.loads(cache.read_text())
    assert collapse_mod.current(project) == scenes
    project.save(project.to_yaml_text().replace("cel-shaded", "watercolor"))
    assert collapse_mod.current(project) != scenes
    assert json.loads(cache.read_text())["key"] != first["key"]


def test_style_edit_makes_every_scene_stale(config, workspace):
    from reelstudio import collapse as collapse_mod

    project = _project(config)
    _render_all_and_record(project, config)
    assert _stale(project, config) == []

    # the active style reaches EVERY prompt: one edit cascades to all scenes
    project.save(project.to_yaml_text().replace(
        "clean bold line art", "watercolor washes"))
    assert collapse_mod.current(project) is not None
    assert _stale(project, config) == ["s1_ramen", "s2_bowldrop", "s3_pinkburst"]

    # ...and switching the active style is the same operation
    project.save(project.to_yaml_text().replace("style: anime", "style: pixar"))
    assert _stale(project, config) == ["s1_ramen", "s2_bowldrop", "s3_pinkburst"]


def test_location_edit_marks_only_its_scenes(config, workspace):
    from reelstudio import collapse as collapse_mod

    project = _project(config)
    _render_all_and_record(project, config)
    assert _stale(project, config) == []

    project.save(project.to_yaml_text().replace(
        "warm orange sky", "warm dawn sky"))
    assert _stale(project, config) == ["s1_ramen"]


def test_still_and_upstream_edits_cascade(config, workspace):
    from reelstudio import generate

    project = _project(config)
    _render_all_and_record(project, config)
    assert _stale(project, config) == []

    # a changed still invalidates the scenes that anchor on it
    (workspace / "stills" / "impact_still_.png").write_bytes(b"changed")
    assert "s3_pinkburst" in _stale(project, config)
    assert "s1_ramen" not in _stale(project, config)

    # an upstream re-render moves the prev_last anchor: the dependent follows,
    # while the still-dependent scene stays stale until it is re-rendered too
    generate.run_job(project, None, str(config.work_dir), "scene", "s1_ramen")
    assert _stale(project, config) == ["s2_bowldrop", "s3_pinkburst"]

def test_manifest_carries_the_collapse(config, workspace):
    from reelstudio import manifest as manifest_mod

    project = _project(config)
    _render_all_and_record(project, config)
    entry = manifest_mod.load(project.meta["reel_dir"])["scenes"]["s2_bowldrop"]
    assert entry["generation"]["prompt"].startswith("2D anime")
    assert entry["generation"]["first"]["kind"] == "prev_last"
    assert entry["generation"]["first"]["file_hash"] != "missing"


def test_workspaces_without_collapse_fall_back_to_hashes(config, workspace):
    """An older workspace reel.py (no collapse subcommand) keeps the hash
    chain working — and its manifest entries record no generation artifact."""
    from reelstudio import collapse as collapse_mod
    from reelstudio import manifest as manifest_mod
    from reelstudio import timeline

    # strip the collapse subcommand from the stub
    script = workspace / "reel.py"
    script.write_text(script.read_text().replace('elif cmd == "collapse":',
                                                 'elif cmd == "nope":'))
    assert collapse_mod.fresh(_project(config)) is None
    assert collapse_mod.current(_project(config)) is None

    project = _project(config)
    _render_all_and_record(project, config)
    entry = manifest_mod.load(project.meta["reel_dir"])["scenes"]["s1_ramen"]
    assert "generation" not in entry
    assert _stale(project, config) == []
    # the hash fallback still catches config edits
    from reelstudio.timeline import chain_hash

    manifest_mod.record_scene(project.meta["reel_dir"], "s1_ramen",
                              "stale-hash", "s1_ramen_00001_.mp4", 22)
    assert timeline.stale_scenes(
        project, manifest_mod.load(project.meta["reel_dir"]),
        project.meta["reel_dir"], collapse=None) == ["s1_ramen"]
    assert chain_hash(project, project.scenes[0])  # fallback machinery intact


def test_adopt_vouches_with_the_collapse(config, workspace):
    """Adopting pre-app renders caches their collapse, so adopted scenes are
    current — and an edited style still invalidates them."""
    from reelstudio import collapse as collapse_mod
    from reelstudio import manifest as manifest_mod

    project = _project(config)
    _render_all_and_record(project, config)
    manifest = manifest_mod.load(project.meta["reel_dir"])
    for sid in manifest["scenes"]:
        del manifest["scenes"][sid]["generation"]
    manifest_mod.save(project.meta["reel_dir"], manifest)
    adopted = manifest_mod.adopt_existing(project.meta["reel_dir"], project)
    assert adopted == 0  # entries exist; adopt only fills empty ones

    manifest = manifest_mod.load(project.meta["reel_dir"])
    for sid in list(manifest["scenes"]):
        manifest["scenes"].pop(sid)
    manifest_mod.save(project.meta["reel_dir"], manifest)
    adopted = manifest_mod.adopt_existing(project.meta["reel_dir"], project)
    assert adopted == 3
    entry = manifest_mod.load(project.meta["reel_dir"])["scenes"]["s1_ramen"]
    assert entry["generation"] == collapse_mod.current(project)["s1_ramen"]
    assert _stale(project, config) == []
