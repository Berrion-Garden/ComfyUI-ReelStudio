"""Still slug resolution: legacy paths, the pick label, unique pool slugs,
ambiguity reporting — project.still_path and the anchor_still pick flow."""

import json


def _pool(ws, *parts):
    """A pool image (the resolver checks existence and name, not pixels)."""
    p = ws.joinpath(*parts)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"x")
    return p


def _label(ws, still_dir, path, *labels):
    from reelstudio import assets as assets_mod

    assets_mod.set_labels(ws, still_dir, str(path), list(labels))


def _project(config):
    from reelstudio.project import load

    return load(config)


def test_unique_pool_slug_resolves(config, workspace):
    from reelstudio import project as pmod

    face = _pool(workspace, "characters", "tony", "posed_stills", "face_.png")
    project = _project(config)
    project.raw["scenes"][1]["video"]["first"] = "still:face"
    assert project.still_path("face") == face
    # a ref resolving through the pool is valid without any map entry
    assert "unknown still ref" not in pmod.validate(project) + project.warnings()


def test_label_pick_resolves_over_ambiguous_pool(config, workspace):
    still_dir = workspace / "stills"
    _pool(workspace, "characters", "tony", "posed_stills",
          "pick1_opt1_r300000_00001_.png")
    opt2 = _pool(workspace, "characters", "tony", "posed_stills",
                 "pick1_opt2_r300001_00001_.png")
    # the operator's pick among the generated options is the label
    _label(workspace, still_dir, opt2, "posed", "still:pick1")

    project = _project(config)
    assert project.still_path("pick1") == opt2
    assert project.still_candidates("pick1") == []


def test_ambiguous_slug_resolves_to_none_and_warns(config, workspace):
    from reelstudio import project as pmod

    _pool(workspace, "backgrounds", "campus_sunset", "plate_a.png")
    _pool(workspace, "backgrounds", "campus_sunset", "plate_b.png")
    project = _project(config)
    project.raw["scenes"][1]["video"]["first"] = "still:plate"

    assert project.still_path("plate") is None
    assert {c.name for c in project.still_candidates("plate")} == \
        {"plate_a.png", "plate_b.png"}

    # ambiguous is a warning naming the candidates, not an error
    warnings = pmod.validate(project)
    assert any("ambiguous" in w and "plate_a.png" in w and "plate_b.png" in w
               for w in warnings)


def test_missing_name_resolves_to_none_without_candidates(config):
    project = _project(config)
    assert project.still_path("never_made") is None
    assert project.still_candidates("never_made") == []


def test_legacy_absolute_path_resolves(config, workspace):
    ref = _pool(workspace, "characters", "Amun", "Amun_rainy.webp")
    project = _project(config)
    project.raw["stills"]["amun_rainy"] = str(ref)
    assert project.still_path("amun_rainy") == ref


def test_legacy_workspace_relative_path_resolves(config, workspace):
    ref = _pool(workspace, "characters", "Amun", "Amun_rainy.webp")
    project = _project(config)
    project.raw["stills"]["amun_rainy"] = "characters/Amun/Amun_rainy.webp"
    assert project.still_path("amun_rainy") == ref


def test_legacy_stale_entry_falls_through_to_the_label(config, workspace):
    face = _pool(workspace, "characters", "tony", "posed_stills", "face_.png")
    _label(workspace, workspace / "stills", face, "posed", "still:face_pick")
    project = _project(config)
    project.raw["stills"]["face_pick"] = "stale/missing.webp"
    # the app figures it out: the path is dead, the label owns the pick
    assert project.still_path("face_pick") == face


def test_legacy_stale_entry_rescued_by_its_own_basename(config, workspace):
    face = _pool(workspace, "characters", "tony", "posed_stills", "face_.png")
    project = _project(config)
    # a path written from another root: only the basename survives
    project.raw["stills"]["face_pick"] = \
        "amuns-reveal/characters/tony/posed_stills/face_.png"
    assert project.still_path("face_pick") == face


def test_label_pick_needs_no_stills_map_entry(config, workspace):
    """A label-picked anchor shows up wherever the legacy map showed — the
    read model's present-signal and the index's scenes group ride the refs,
    not the map."""
    from reelstudio import assets as assets_mod
    from reelstudio.app import ReelStudio
    from reelstudio.readmodel import project_view

    face = _pool(workspace, "characters", "tony", "posed_stills", "face_.png")
    _label(workspace, workspace / "stills", face, "posed", "still:face_pick")
    project = _project(config)
    project.raw["scenes"][0]["video"]["first"] = "still:face_pick"
    project.save()  # project_view re-derives from disk

    data = assets_mod.index_assets(workspace, project)
    by_slug = {a["slug"]: a for a in data["groups"]["scenes"]}
    assert by_slug["face"]["used_by"] == ["s1_ramen"]
    assert "still:face_pick" in by_slug["face"]["labels"]

    view = project_view(ReelStudio(config))
    assert view["stills"]["face_pick"] is True
    assert "face_pick" in view["stills"]  # in play, though not in the map


async def test_anchor_still_tool_wires_label_not_paths(config, workspace):
    """The pick flow end to end: label on the chosen file, scene ref wired,
    the legacy `stills:` path entry for that name gone, other entries kept."""
    import yaml as yaml_mod

    from reelstudio.agent.tools import ToolBox
    from reelstudio.app import ReelStudio
    from reelstudio.project import load

    pool = workspace / "characters" / "tony" / "posed_stills"
    pool.mkdir(parents=True)
    opt1 = pool / "tony_dunk01_00001_.png"
    opt1.write_bytes(b"x")
    opt2 = pool / "tony_dunk02_00001_.png"
    opt2.write_bytes(b"x")

    # the legacy world: a path entry for the name exists
    text = config.yaml_path.read_text().replace(
        "stills:\n  opening: opening_still",
        f"stills:\n  dunk_pick: {opt2}\n  opening: opening_still")
    config.yaml_path.write_text(text)

    box = ToolBox(ReelStudio(config))
    out = json.loads(await box.call("anchor_still", {
        "path": f"asset:{opt1}", "scene_id": "s1_ramen",
        "anchor": "first", "name": "dunk_pick"}))
    assert out["ref"] == "still:dunk_pick"
    assert out["removed_stills_entry"] is True
    assert out["picked"]["picked"] == \
        "characters/tony/posed_stills/tony_dunk01_00001_.png"

    raw = yaml_mod.safe_load(config.yaml_path.read_text())
    assert raw["scenes"][0]["video"]["first"] == "still:dunk_pick"
    assert "dunk_pick" not in raw["stills"]  # the path entry went
    assert raw["stills"]["opening"] == "opening_still"  # the others stayed
    # the yaml never grows absolute paths (meta.wiring aside)
    assert all("/" not in str(v) for v in raw["stills"].values())

    # the pick is the label in assets.yaml, and it re-resolves
    labels = yaml_mod.safe_load((workspace / "assets.yaml").read_text())["labels"]
    assert "still:dunk_pick" in \
        labels["characters/tony/posed_stills/tony_dunk01_00001_.png"]

    # a re-pick moves the label — a name anchors exactly one file
    out = json.loads(await box.call("anchor_still", {
        "path": f"asset:{opt2}", "scene_id": "s1_ramen",
        "anchor": "first", "name": "dunk_pick"}))
    assert out["picked"]["released"] == \
        ["characters/tony/posed_stills/tony_dunk01_00001_.png"]
    labels = yaml_mod.safe_load((workspace / "assets.yaml").read_text())["labels"]
    assert "still:dunk_pick" in \
        labels["characters/tony/posed_stills/tony_dunk02_00001_.png"]
    assert "still:dunk_pick" not in \
        labels.get("characters/tony/posed_stills/tony_dunk01_00001_.png", [])
    project = load(config)
    assert project.still_path("dunk_pick") == opt2

    # guards: unknown scene and a bogus anchor never touch anything
    refused = json.loads(await box.call("anchor_still", {
        "path": f"asset:{opt1}", "scene_id": "nope", "anchor": "first"}))
    assert "error" in refused and "known_scenes" in refused
    refused = json.loads(await box.call("anchor_still", {
        "path": f"asset:{opt1}", "scene_id": "s1_ramen",
        "anchor": "middle"}))
    assert "anchor must be" in refused["error"]
