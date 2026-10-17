"""reel.yaml structure rules: chain agreement, anchors, music, warnings."""

import yaml


def test_valid_workspace_loads(config):
    from reelstudio.project import load

    project = load(config)
    assert [s["id"] for s in project.scenes] == ["s1_ramen", "s2_bowldrop", "s3_pinkburst"]


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


def test_unknown_still_ref_rejected(config):
    from reelstudio.errors import ValidationError
    from reelstudio.project import Project, validate

    project = Project(yaml.safe_load(config.yaml_path.read_text()), config)
    project.raw["scenes"][1]["video"]["first"] = "still:nope"
    try:
        validate(project)
        raise AssertionError("expected ValidationError")
    except ValidationError as e:
        assert any("unknown still ref" in p for p in e.problems)


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
    assert project.still_path("opening").name == "opening_still_.png"
