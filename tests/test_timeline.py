"""Timeline math and the staleness cascade."""

from reelstudio import manifest as manifest_mod


def _project(config):
    from reelstudio.project import load

    return load(config)


def test_scene_durations_read_per_scene_frames(config):
    from reelstudio.timeline import scene_dur, scene_frames

    project = _project(config)
    assert scene_frames(project, project.scenes[0]) == 22
    assert scene_dur(project, project.scenes[0]) == round(22 / 24, 4)


def test_starts_are_cumulative(config):
    """Starts accumulate per-scene durations (documented rule: the sum of the
    rounded per-scene durations, not a recomputation from frames)."""
    from reelstudio.timeline import scene_starts, total_dur

    project = _project(config)
    d = round(22 / 24, 4)
    assert scene_starts(project) == [0.0, d, round(2 * d, 4)]
    assert total_dur(project) == round(3 * d, 4)


def test_config_edits_change_the_generation_view(config):
    """The generation view is what collapse hashes — editing a scene's
    description must change it (and therefore staleness downstream)."""
    from reelstudio.timeline import generation_view

    project = _project(config)
    s2 = project.scene("s2_bowldrop")
    before = generation_view(project, s2)
    s2["video"]["description"] = "Changed."
    assert generation_view(project, s2) != before


def test_staleness_reflects_manifest(config, workspace):
    """Staleness is one mechanism: the manifest's recorded generation input
    diffed against the fresh collapse; a missing deliverable stays stale."""
    from pathlib import Path

    from reelstudio import collapse as collapse_mod
    from reelstudio.manifest import load as load_manifest
    from reelstudio.manifest import record_scene
    from reelstudio.timeline import stale_scenes

    project = _project(config)
    reel_dir = project.meta["reel_dir"]
    Path(reel_dir).mkdir(parents=True, exist_ok=True)
    for s in project.scenes:
        (Path(reel_dir) / f"{s['id']}_00001_.mp4").write_bytes(b"x")
    # the collapse (and its cache) sees the deliverables the manifest will record
    collapse = collapse_mod.current(project)
    assert collapse is not None
    assert stale_scenes(project, {"scenes": {}}, reel_dir, collapse) == \
        [s["id"] for s in project.scenes]

    for s in project.scenes:
        (Path(reel_dir) / f"{s['id']}_00001_.mp4").write_bytes(b"x")
        record_scene(reel_dir, s["id"], f"{s['id']}_00001_.mp4", 22,
                     generation=collapse[s["id"]])
    manifest = load_manifest(reel_dir)
    assert stale_scenes(project, manifest, reel_dir, collapse) == []

    # a config edit moves the fresh collapse: exactly the edited cascade stales
    (workspace / "reel.yaml").write_text(
        (workspace / "reel.yaml").read_text().replace(
            "The fox eats noodles.", "The fox devours noodles."))
    fresh = collapse_mod.fresh(_project(config))
    assert fresh is not None
    assert stale_scenes(project, manifest, reel_dir, fresh) == ["s1_ramen"]


def test_generation_view_folds_shared_looks(config, workspace):
    """The active style is part of every scene's generation identity; a
    location only of the scenes referencing it. This is what makes one style
    edit mark the whole reel stale — hash fallback included."""
    from reelstudio.timeline import generation_view

    project = _project(config)
    s1, s2 = project.scenes[0], project.scenes[1]
    v1, v2 = generation_view(project, s1), generation_view(project, s2)
    assert v1["style"]["pro"].startswith("2D anime")
    assert v1["location"]["pro"].startswith("university campus")
    assert v2["location"]["pro"].startswith("the campus at first light")  \
        # s2 folds its own location, not s1's

    project.save(config.yaml_path.read_text().replace(
        "cel-shaded", "watercolor washes"))
    assert generation_view(project, s1) != v1
    assert generation_view(project, s2) != v2  # global: both changed

    v2_watercolor = generation_view(project, s2)
    project.save(config.yaml_path.read_text().replace(
        "warm orange sky", "warm dawn sky"))
    assert generation_view(project, s1) != v1
    assert generation_view(project, s2) == v2_watercolor  # scoped: only s1 moved


def test_anchor_resolution(config):
    from reelstudio.timeline import resolve_anchor

    project = _project(config)
    assert resolve_anchor(project, None)["kind"] == "none"
    assert resolve_anchor(project, "prev_last")["kind"] == "prev_last"
    still = resolve_anchor(project, "still:opening")
    assert still["kind"] == "still" and still["path"].endswith("opening_.png")
