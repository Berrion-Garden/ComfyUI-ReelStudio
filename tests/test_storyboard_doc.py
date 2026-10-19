"""Breakdown document validation — the single-source-of-truth contract.

The breakdown yaml owns every trait of a production's pose/plate campaign.
These tests pin the invariants on a data structure, not on text: duplicate
keys raise at load, references resolve, no implicit defaults, no dead
definitions, and the composer performs the documented inheritance.

Every test builds a fresh deep copy of the fixture — order independence.

The operator's Amunrekh breakdown is exercised live (skipped when the file
is absent, e.g. on CI).
"""

import copy

from pathlib import Path

import pytest
import yaml

from reelstudio.storyboard_doc import (StrictLoader, check_scene_yaml,
                                       compose_plate, compose_still, emit,
                                       emit_scene_yaml, load, validate)

AMUNREKH_DOC = Path("/home/kyle/Desktop/amunrekh_breakdown.yaml")

GOOD_DOC = {
    "style": "test style",
    "characters": {
        "test": {
            "attributes": {"eyes": "green", "expression": "calm",
                           "negatives": ["hair"]},
            "backdrop": "blank",
        },
    },
    "outfits": {"base": {"clothing": "tunic", "carried": "a satchel"}},
    "props": {"lamp": "an oil lamp"},
    "effects": {"glow": "soft golden glow"},
    "places": {"room": {"pro": "INT a plain room", "con": ["outdoors"]}},
    "times": {"day": {"pro": "bright daylight", "con": ["night"]}},
    "plates": {"room_day": {"place": "room", "time": "day"}},
    "scenes": [{
        "title": "Only",
        "plates": ["room_day"],
        "variants": {
            "test_still": {
                "outfit": "base",
                "pose": "standing, holding the lamp up",
                "held": ["lamp"],
                "effects": ["glow"],
                "expression": "bright",
            },
        },
    }],
}


def _doc() -> dict:
    """A fresh deep copy per test — no test may mutate the fixture."""
    return copy.deepcopy(GOOD_DOC)


def _doc_without_variant_key(key):
    doc = _doc()
    doc["scenes"][0]["variants"]["test_still"].pop(key)
    return doc


def test_good_doc_validates_clean():
    ok, findings = validate(_doc())
    assert ok, "\n".join(findings)


def test_load_raises_on_duplicate_key():
    text = "style: a\noutfits:\n  base:\n    clothing: x\n    clothing: y\n"
    with pytest.raises(yaml.YAMLError, match="duplicate key"):
        yaml.load(text, Loader=StrictLoader)


def test_merge_override_keeps_explicit_and_never_raises():
    """The production yaml's leaf clones ({<<: *ref, seed: N}) are overrides,
    not duplicates — and the explicit value must WIN."""
    text = ("clones:\n"
            "  - &ref\n"
            "    slug: a\n"
            "    seed: 300000\n"
            "  - {<<: *ref, seed: 307919}\n"
            "  - <<: *ref\n"
            "    seed: 315838\n")
    doc = yaml.load(text, Loader=StrictLoader)
    assert doc["clones"][1]["seed"] == 307919
    assert doc["clones"][2]["seed"] == 315838
    assert doc["clones"][1]["slug"] == "a"          # inherited graft


def test_merge_chain_and_sequence_earlier_wins():
    text = ("base1: &b1\n  x: 1\n  y: 2\n"
            "base2: &b2\n  y: 3\n  z: 4\n"
            "leaf:\n  <<: [*b1, *b2]\n  x: 9\n")
    assert yaml.load(text, Loader=StrictLoader)["leaf"] == \
        {"x": 9, "y": 2, "z": 4}


def test_missing_top_level_key():
    doc = _doc()
    del doc["times"]
    ok, findings = validate(doc)
    assert not ok
    assert any("times" in f for f in findings)


def test_variant_reference_rules():
    cases = {
        "unknown outfit": lambda v: v.update(outfit="ghost"),
        "missing outfit": lambda v: v.pop("outfit"),
        "missing pose": lambda v: v.pop("pose"),
        "unknown prop": lambda v: v.update(held=["ghost"]),
        "unknown effect": lambda v: v.update(effects=["ghost"]),
        "unknown variant key": lambda v: v.update(stancce="typo"),
    }
    for name, mutate in cases.items():
        doc = _doc()
        mutate(doc["scenes"][0]["variants"]["test_still"])
        ok, findings = validate(doc)
        assert not ok, name
        assert any(name.split()[0] in f or "unknown keys" in f
                   for f in findings), (name, findings)
    doc = _doc()
    doc["scenes"][0]["variants"]["test_still"]["outfit"] = "ghost"
    ok, findings = validate(doc)
    assert any("unknown outfit 'ghost'" in f for f in findings)


def test_plate_rules():
    cases = {
        "missing 'time'": lambda p: p.pop("time"),
        "missing 'place'": lambda p: p.pop("place"),
        "unknown time": lambda p: p.update(time="ghost_time"),
        "unknown place": lambda p: p.update(place="ghost_place"),
        "unknown plate keys": lambda p: p.update(shot="oops"),
    }
    for name, mutate in cases.items():
        doc = _doc()
        mutate(doc["plates"]["room_day"])
        ok, findings = validate(doc)
        assert not ok, name
        assert any(name.split()[0] in f for f in findings), \
            (name, findings)
    doc = _doc()
    doc["scenes"][0]["plates"].append("ghost_plate")
    ok, findings = validate(doc)
    assert any("unknown plate 'ghost_plate'" in f for f in findings)


def test_dead_definitions_are_findings():
    doc = _doc()
    doc["scenes"][0]["variants"]["test_still"].pop("held")
    ok, findings = validate(doc)
    assert any("dead prop: 'lamp'" in f for f in findings)

    doc = _doc()
    doc["scenes"][0]["variants"]["test_still"].pop("effects")
    ok, findings = validate(doc)
    assert any("dead effect: 'glow'" in f for f in findings)

    doc = _doc()
    doc["scenes"][0]["variants"]["test_still"]["outfit"] = "ghost"
    doc["outfits"]["ghost"] = {"clothing": "x"}
    doc["scenes"][0]["variants"]["test_still"]["held"] = ["lamp"]
    ok, findings = validate(doc)
    assert any("dead outfit: 'base'" in f for f in findings)

    doc = _doc()
    doc["scenes"][0]["plates"] = ["ghost_plate"]
    ok, findings = validate(doc)
    assert any("dead plate: 'room_day'" in f for f in findings)

    doc = _doc()
    doc["plates"]["room_day"]["place"] = "ghost_place"
    ok, findings = validate(doc)
    assert any("dead place: 'room'" in f for f in findings)

    doc = _doc()
    doc["plates"]["room_day"]["time"] = "ghost_time"
    ok, findings = validate(doc)
    assert any("dead time: 'day'" in f for f in findings)


def test_duplicate_variant_slug_across_scenes():
    doc = _doc()
    doc["scenes"].append(copy.deepcopy(doc["scenes"][0]))
    ok, findings = validate(doc)
    assert not ok
    assert any("duplicate variant slug 'test_still'" in f for f in findings)


def test_outfit_missing_clothing_and_place_missing_pro():
    doc = _doc()
    doc["outfits"]["base"] = {"worn": "socks"}
    ok, findings = validate(doc)
    assert any("outfit 'base': missing 'clothing'" in f for f in findings)

    doc = _doc()
    doc["places"]["room"] = {"con": ["outdoors"]}
    ok, findings = validate(doc)
    assert any("place 'room': missing 'pro'" in f for f in findings)


def test_compose_still_performs_the_inheritance():
    composed = compose_still(_doc(), "test_still")
    text = composed["prompt"]
    assert "test style" in text
    assert "blank" in text
    assert "green" in text
    assert "tunic" in text                      # outfit trait composed in
    assert "an oil lamp" in text                # held -> prop description
    assert "a satchel" not in text              # held REPLACES carried
    assert "soft golden glow" in text           # effects composed in
    assert "expression: bright" in text         # variant overrides canon
    assert "expression: calm" not in text
    assert composed["negative"] == "hair"


def test_compose_still_inherits_canon_expression_when_variant_omits_it():
    doc = _doc()
    doc["scenes"][0]["variants"]["test_still"].pop("expression")
    composed = compose_still(doc, "test_still")
    assert "expression: calm" in composed["prompt"]


def test_compose_plate_merges_place_time_extra():
    composed = compose_plate(_doc(), "room_day")
    assert "INT a plain room" in composed["prompt"]
    assert "bright daylight" in composed["prompt"]
    assert composed["negative"] == "outdoors, night"

    doc = _doc()
    doc["plates"]["room_day"]["extra"] = "a skylight"
    assert "a skylight" in compose_plate(doc, "room_day")["prompt"]


def test_emit_renders_every_slug_and_refuses_invalid_docs():
    sheet = emit(_doc())
    assert "test_still" in sheet and "room_day" in sheet
    doc = _doc()
    doc["scenes"][0]["variants"]["test_still"]["outfit"] = "ghost"
    with pytest.raises(ValueError, match="invalid"):
        emit(doc)


def test_emit_scene_yaml_and_check_roundtrip():
    scene = yaml.safe_load("""
meta:
  comfy: http://localhost:8188

styles:
  cinematic:
    pro: test style
style: cinematic

characters:
  test:
    backdrop: blank
    attributes:
      eyes: green
      expression: calm
      negatives: "hair"
    layers:
      base:
        clothing: tunic
        carried: a satchel
    seeds: [1]
    variants:
      - slug: test_reference
        layer: base
        pose: "standing neutral, full body"
        seed: 100
      - slug: test_still
        layer: base
        pose: standing, holding the lamp up
        expression: bright
        held: an oil lamp
        effects: soft golden glow
        seed: 200
locations:
  room_day:
    pro: "INT a plain room. Bright daylight"
""")
    ok, findings = check_scene_yaml(_doc(), scene)
    assert ok, "\n".join(findings)
    # and the emitter produces the same text the seat can graft
    blocks = emit_scene_yaml(_doc())
    assert blocks["characters"]["test"]["attributes"]["negatives"] == "hair"
    assert "worn" not in blocks["characters"]["test"]["layers"]["base"]
    leaf = blocks["characters"]["test"]["variants"][0]
    assert leaf["slug"] == "test_still" and "seed" not in leaf
    assert blocks["locations"]["room_day"]["pro"] == \
        "INT a plain room. Bright daylight"


def test_scene_yaml_staleness_is_reported_by_name():
    scene = yaml.safe_load("""
characters:
  test:
    backdrop: blank
    attributes:
      eyes: green
      expression: calm
      negatives: "hair"
    layers:
      base:
        clothing: tunic
    variants:
      - slug: test_reference
        layer: base
        pose: "standing neutral, full body"
      - slug: test_still
        layer: base
        pose: standing, holding a DIFFERENT lamp
        expression: bright
locations:
  room_day:
    pro: "INT a plain room. Bright daylight"
""")
    ok, findings = check_scene_yaml(_doc(), scene)
    assert not ok
    assert any("leaf drift on 'test_still.pose'" in f for f in findings)
    assert any("held missing" in f or "'test_still.held'" in f
               for f in findings)
    assert any("test_reference" not in f for f in findings)


def test_scene_yaml_missing_leaf_and_unknown_layer():
    scene = yaml.safe_load("""
characters:
  test:
    backdrop: blank
    attributes: {eyes: green, expression: calm, negatives: "hair"}
    layers:
      ghost_layer: {clothing: x}
      base: {clothing: tunic}
    variants:
      - slug: test_reference
        layer: base
        pose: "standing neutral, full body"
locations:
  room_day:
    pro: "INT a plain room. Bright daylight"
""")
    ok, findings = check_scene_yaml(_doc(), scene)
    assert not ok
    assert any("leaf missing: test_still" in f for f in findings)
    assert any("unknown layer 'ghost_layer'" in f for f in findings)


def test_scene_yaml_location_drift_and_unknown_location():
    scene = yaml.safe_load("""
characters:
  test:
    backdrop: blank
    attributes: {eyes: green, expression: calm, negatives: "hair"}
    layers: {base: {clothing: tunic}}
    variants:
      - slug: test_still
        layer: base
        pose: standing, holding the lamp up
        expression: bright
        held: an oil lamp
        effects: soft golden glow
locations:
  room_day:
    pro: "INT a plain room. Bright daylight, plus a skylight"
  ghost_location:
    pro: somewhere
""")
    ok, findings = check_scene_yaml(_doc(), scene)
    assert not ok
    assert any("location drift on 'room_day'" in f for f in findings)
    assert any("unknown location 'ghost_location'" in f for f in findings)


def test_scene_yaml_attribute_drift_names_the_key():
    scene = yaml.safe_load("""
characters:
  test:
    backdrop: blank
    attributes: {eyes: blue, expression: calm, negatives: "hair"}
    layers: {base: {clothing: tunic}}
    variants:
      - slug: test_still
        layer: base
        pose: standing, holding the lamp up
        expression: bright
        held: an oil lamp
        effects: soft golden glow
locations: {room_day: {pro: "INT a plain room. Bright daylight"}}
""")
    ok, findings = check_scene_yaml(_doc(), scene)
    assert not ok
    assert any("attribute drift on 'eyes'" in f for f in findings)


@pytest.mark.skipif(not AMUNREKH_DOC.exists(),
                    reason="operator's breakdown not on this machine")
def test_live_amunrekh_breakdown_validates_and_emits():
    doc = load(AMUNREKH_DOC)
    ok, findings = validate(doc)
    assert ok, "\n".join(findings)
    sheet = emit(doc)
    for scene in doc["scenes"]:
        for slug in scene["variants"]:
            assert slug in sheet
    for slug in doc["plates"]:
        assert slug in sheet
    for slug in ("amunrekh_hooded_scowl", "amunrekh_precise_dodge",
                 "amunrekh_kyudo_full_draw", "amunrekh_title_frame"):
        composed = compose_still(doc, slug)
        assert composed["negative"], "canon negatives must ride the negative"
