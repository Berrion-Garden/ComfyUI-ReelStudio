"""reel.yaml structure rules: chain agreement, anchors, music, warnings."""

import yaml


def test_valid_workspace_loads(config):
    from reelstudio.project import load

    project = load(config)
    assert [s["id"] for s in project.scenes] == ["s1_ramen", "s2_bowldrop", "s3_pinkburst"]
    assert project.active_style_name == "anime"
    assert project.active_style()["pro"].startswith("2D anime")
    assert project.scene_location(project.scenes[0])["pro"].startswith("university campus")


def test_look_blocks_reject_bad_refs_and_aliases(config, workspace):
    import pytest

    from reelstudio.errors import ValidationError
    from reelstudio.project import load

    project = load(config)
    raw = config.yaml_path.read_text()
    with pytest.raises(ValidationError) as e:
        project.save(raw.replace("style: anime", "style: pixar2"))
    assert any("known: ['anime', 'pixar']" in p for p in e.value.problems)

    with pytest.raises(ValidationError) as e:
        project.save(raw.replace("style: anime\n", ""))
    assert any("pick the active style" in p for p in e.value.problems)

    with pytest.raises(ValidationError) as e:
        project.save(raw.replace("pro: 2D anime, cel-shaded, clean bold line art, vibrant flat colors",
                                 "pro: 2D anime, {foks}"))
    assert any("unknown alias ref" in p and "'foks'" in p
               for p in e.value.problems)

    with pytest.raises(ValidationError) as e:
        project.save(raw.replace("    location: campus_sunset", "    location: dojo"))
    assert any("unknown location 'dojo'" in p for p in e.value.problems)

    with pytest.raises(ValidationError) as e:
        project.save(raw.replace(
            "locations:\n"
            "  campus_sunset:\n"
            "    pro: university campus plaza at golden sunset, warm orange sky\n"
            "    con: indoor, night, rain\n",
            "locations: [nope]\n"))
    assert any("must be a map" in p for p in e.value.problems)

    with pytest.raises(ValidationError) as e:
        project.save(raw.replace("meta:\n", "meta: [broken\n"))
    assert any("malformed yaml" in p for p in e.value.problems)


def test_look_blocks_are_optional(config, workspace):
    """A yaml with no styles/locations at all stays valid — the machinery is
    additive."""
    import yaml

    from reelstudio.project import load

    project = load(config)
    raw = yaml.safe_load(config.yaml_path.read_text())
    for key in ("styles", "style", "locations"):
        raw.pop(key, None)
    for s in raw["scenes"]:
        s.pop("location", None)
    project.save(yaml.safe_dump(raw, sort_keys=False, allow_unicode=True))
    assert project.active_style() is None
    assert project.scene_location(project.scenes[0]) is None


def test_off_grid_frames_warn_not_fail(config):
    from reelstudio.project import load

    project = load(config)
    raw = project.raw
    raw["scenes"][0]["frames"] = 45  # off the 17n+5 grid, exactly like the real reel
    problems = []
    import reelstudio.project as pmod

    # validate() raises only on errors; warnings come back
    warnings = pmod.validate(project)
    assert any("17n+5" in w for w in warnings)


def test_chain_break_rejected(config):
    from reelstudio.errors import ValidationError
    from reelstudio.project import Project, validate

    project = Project(yaml.safe_load(config.yaml_path.read_text()), config)
    project.raw["scenes"][0]["next"] = "wrong_scene"
    try:
        validate(project)
        raise AssertionError("expected ValidationError")
    except ValidationError as e:
        assert any("chain break" in p for p in e.problems)


def test_first_scene_cannot_be_prev_last(config):
    from reelstudio.errors import ValidationError
    from reelstudio.project import Project, validate

    project = Project(yaml.safe_load(config.yaml_path.read_text()), config)
    project.raw["scenes"][0]["video"]["first"] = "prev_last"
    try:
        validate(project)
        raise AssertionError("expected ValidationError")
    except ValidationError as e:
        assert any("prev_last" in p for p in e.problems)


def test_unresolvable_still_ref_warns(config):
    """One missing image must never 500 the project: an unresolvable
    `still:` anchor is a warning (the UI shows the bad-load slot), not a
    ValidationError."""
    from reelstudio.project import Project, validate

    project = Project(yaml.safe_load(config.yaml_path.read_text()), config)
    project.raw["scenes"][1]["video"]["first"] = "still:nope"
    warnings = validate(project)
    assert any("still:nope" in w and "no labeled pick" in w for w in warnings)


def test_duplicate_music_names_rejected(config):
    from reelstudio.errors import ValidationError
    from reelstudio.project import Project, validate

    project = Project(yaml.safe_load(config.yaml_path.read_text()), config)
    project.raw["scenes"][0]["music"] = {"name": "dupe", "caption": "a"}
    project.raw["scenes"][1]["music"] = {"name": "dupe", "caption": "b"}
    try:
        validate(project)
        raise AssertionError("expected ValidationError")
    except ValidationError as e:
        assert any("unique" in p for p in e.problems)


def test_still_path_resolves_double_underscore(config):
    from reelstudio.project import load

    project = load(config)
    assert project.still_path("opening").name == "opening_.png"


def test_file_hash_memo_tracks_content_changes(config):
    from reelstudio import project as project_mod

    f = config.workspace / "memo_probe.txt"
    f.write_text("v1")
    h1 = project_mod.file_hash(f)
    assert h1 != "missing"

    # same content, touched mtime -> same hash served from the memo
    import os
    st = f.stat()
    os.utime(f, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000))
    assert project_mod.file_hash(f) == h1

    f.write_text("v2")
    assert project_mod.file_hash(f) != h1
    assert project_mod.file_hash(config.workspace / "absent.txt") == "missing"


def test_load_cached_reparses_only_when_yaml_changes(config):
    from reelstudio.project import load_cached

    a = load_cached(config)
    assert load_cached(config) is a  # warm: same parsed tree

    config.yaml_path.write_text(config.yaml_path.read_text())
    b = load_cached(config)
    assert b is not a  # the write bumped the mtime -> fresh parse
    assert b.raw == a.raw
