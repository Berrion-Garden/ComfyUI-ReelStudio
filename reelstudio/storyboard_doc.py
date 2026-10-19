"""Storyboard breakdown — YAML source of truth for pose/plate generation.

A breakdown file (one per production) is a single YAML document owning every
trait of a pose-still + background-plate campaign: character canon, named
outfits/props/effects, places/times/plates, and per-scene variant maps.
Every trait is defined exactly once and referenced by slug everywhere else.

The inheritance is EXECUTABLE, not prose: `compose_still` / `compose_plate`
perform the merge to emit generation prompts, so the breakdown and the
prompts can never drift. Regeneration is the workflow — never hand-edit the
derived sheet.

Contract (structure rules `validate` checks, findings name the offender):

- top-level: `style` (str), `characters`, `outfits`, `props`, `effects`,
  `places`, `times`, `plates`, `scenes`.
- a character: `attributes` (trait key → text; `negatives` is a list of
  bare concept words) + `backdrop` (blank backdrop text).
- an outfit: a sparse override map over the attributes — a key present
  replaces that trait; everything else inherits. `carried` is the trait a
  pose's `held` replaces.
- a variant (one per pose still), allowed keys exactly:
  `character` (optional, default = the doc's first character), `outfit`
  (required, no implicit defaults), `pose` (required — body/limbs/head),
  `expression` (optional — eyes/face), `held` (prop slugs), `effects`
  (effect slugs).
- a plate (one per background generation): `place` + `time` (required
  slugs) + optional `extra`.
- a scene: `title`, `plates` (list of plate slugs shot on it), `variants`
  (map of slug → variant). Variant slugs are unique across the whole doc.
- no dead definitions: every outfit/prop/effect/place/time/plate is
  referenced at least once.

Merge per still: attributes ← outfit (per-key wholesale) ← variant.
Lists replace, never concatenate. `held` replaces `carried`.

`load` reads a file with a strict YAML loader (duplicate mapping keys raise
— a silent overwrite is a single-source-of-truth bug); `validate` returns
`(ok, findings)`; `compose_still`/`compose_plate` return
`{prompt, negative}`; `emit` renders the derived prompt sheet;
`main` is the CLI: validate, then emit.
"""

from __future__ import annotations

from pathlib import Path

import yaml

_VARIANT_KEYS = {"character", "outfit", "pose", "expression", "held",
                 "effects"}
_PLATE_KEYS = {"place", "time", "extra"}


class StrictLoader(yaml.SafeLoader):
    """SafeLoader that raises on duplicate mapping keys."""

    def construct_mapping(self, node, deep=False):
        loader = self
        loader.flatten_mapping(node)
        mapping = {}
        for key_node, value_node in node.value:
            key = loader.construct_object(key_node, deep=deep)
            if key in mapping:
                raise yaml.constructor.ConstructorError(
                    None, None, f"duplicate key {key!r}", key_node.start_mark)
            mapping[key] = loader.construct_object(value_node, deep=deep)
        return mapping


def load(path) -> dict:
    return yaml.load(Path(path).read_text(encoding="utf-8"),
                     Loader=StrictLoader)


def validate(doc: dict) -> tuple:
    """Returns (ok, findings); findings are human-readable strings."""
    findings: list = []
    for key in ("style", "characters", "outfits", "props", "effects",
                "places", "times", "plates", "scenes"):
        if key not in doc:
            findings.append(f"missing top-level key: {key}")

    def registry(name, required="map"):
        reg = doc.get(name)
        if not isinstance(reg, dict) or not reg:
            findings.append(f"{name} registry must be a non-empty mapping")
            return {}
        return reg

    characters = registry("characters")
    for slug, spec in characters.items():
        if not isinstance(spec, dict) or not isinstance(
                spec.get("attributes"), dict):
            findings.append(f"character {slug!r}: missing 'attributes' map")
            continue
        if not isinstance(spec.get("backdrop"), str):
            findings.append(f"character {slug!r}: missing 'backdrop' "
                            "(blank backdrop text)")
        for key, val in spec["attributes"].items():
            if key == "negatives":
                if not isinstance(val, list) or \
                        not all(isinstance(x, str) for x in val):
                    findings.append(f"character {slug!r}: 'negatives' must "
                                    "be a list of bare concept words")
            elif not isinstance(val, str):
                findings.append(f"character {slug!r}: attribute {key!r} "
                                "must be a string")

    outfits = registry("outfits")
    props = registry("props")
    effects = registry("effects")
    places = registry("places")
    times = registry("times")
    plates = registry("plates")

    for name, reg, required in (("outfit", outfits, "clothing"),
                                ("place", places, "pro"), ("time", times,
                                                          "pro")):
        for slug, spec in reg.items():
            if not isinstance(spec, dict) or required not in spec:
                findings.append(f"{name} {slug!r}: missing '{required}'")
    for name, reg in (("prop", props), ("effect", effects)):
        for slug, desc in reg.items():
            if not isinstance(desc, str) or not desc:
                findings.append(f"{name} {slug!r}: must be a text "
                                "description")

    for slug, spec in plates.items():
        where = f"plate {slug!r}"
        if not isinstance(spec, dict):
            findings.append(f"{where}: must be a mapping")
            continue
        unknown = set(spec) - _PLATE_KEYS
        if unknown:
            findings.append(f"{where}: unknown keys {sorted(unknown)} — "
                            "allowed: place, time, extra")
        for key in ("place", "time"):
            if key not in spec:
                findings.append(f"{where}: missing '{key}' — every plate "
                                "names its place and time, no implicit "
                                "defaults")
            elif spec[key] not in (places if key == "place" else times):
                findings.append(f"{where}: unknown {key} {spec[key]!r}")

    first_character = next(iter(characters), None)
    seen_variants = set()
    used_outfits, used_props, used_effects, used_plates = set(), set(), \
        set(), set()
    scenes = doc.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        findings.append("scenes must be a non-empty list")
        scenes = []
    for scene in scenes:
        title = scene.get("title", "<untitled>") \
            if isinstance(scene, dict) else "<untitled>"
        where = f"scene {title!r}"
        if not isinstance(scene, dict):
            findings.append(f"{where}: must be a mapping")
            continue
        scene_plates = scene.get("plates")
        if not isinstance(scene_plates, list) or not scene_plates:
            findings.append(f"{where}: missing 'plates' list")
            scene_plates = []
        for x in scene_plates:
            if x not in plates:
                findings.append(f"{where}: unknown plate {x!r}")
            used_plates.add(x)
        variants = scene.get("variants")
        if not isinstance(variants, dict) or not variants:
            findings.append(f"{where}: missing 'variants' map")
            continue
        for slug, spec in variants.items():
            if slug in seen_variants:
                findings.append(f"duplicate variant slug {slug!r} "
                                f"({where})")
            seen_variants.add(slug)
            where_v = f"scene {title!r} variant {slug!r}"
            if not isinstance(spec, dict):
                findings.append(f"{where_v}: must be a mapping")
                continue
            unknown = set(spec) - _VARIANT_KEYS
            if unknown:
                findings.append(f"{where_v}: unknown keys {sorted(unknown)} "
                                "— allowed: character, outfit, pose, "
                                "expression, held, effects")
            if "pose" not in spec:
                findings.append(f"{where_v}: missing 'pose'")
            elif not isinstance(spec["pose"], str):
                findings.append(f"{where_v}: 'pose' must be a string")
            if "outfit" not in spec:
                findings.append(f"{where_v}: missing 'outfit' — every pose "
                                "names its outfit, no implicit defaults")
            elif spec["outfit"] not in outfits:
                findings.append(f"{where_v}: unknown outfit "
                                f"{spec['outfit']!r}")
            used_outfits.add(spec.get("outfit"))
            for key, reg, reg_name in (("held", props, "prop"),
                                       ("effects", effects, "effect")):
                val = spec.get(key)
                if val is None:
                    continue
                if not isinstance(val, list) or \
                        not all(isinstance(x, str) for x in val):
                    findings.append(f"{where_v}: '{key}' must be a list of "
                                    f"{reg_name} slugs")
                    continue
                for x in val:
                    if x not in reg:
                        findings.append(f"{where_v}: unknown {reg_name} "
                                        f"{x!r}")
                    if reg is props:
                        used_props.add(x)
                    else:
                        used_effects.add(x)
            if "expression" in spec and \
                    not isinstance(spec["expression"], str):
                findings.append(f"{where_v}: 'expression' must be a string")

    for name, reg, used in (("outfit", outfits, used_outfits),
                            ("prop", props, used_props),
                            ("effect", effects, used_effects)):
        for slug in reg:
            if slug not in used:
                findings.append(f"dead {name}: {slug!r} is defined but "
                                "never referenced by a pose")
    for name, reg, slot, target in (("place", places, "place", plates),
                                    ("time", times, "time", plates)):
        for slug in reg:
            if not any(isinstance(p, dict) and p.get(slot) == slug
                       for p in target.values()):
                findings.append(f"dead {name}: {slug!r} is defined but "
                                "never referenced by a plate")
    for slug in plates:
        if slug not in used_plates:
            findings.append(f"dead plate: {slug!r} is defined but never "
                            "referenced by a scene")
    if first_character is None:
        findings.append("no characters defined")

    return not findings, findings


def _find_variant(doc, slug):
    for scene in doc.get("scenes", []):
        variants = scene.get("variants", {}) if isinstance(scene, dict) \
            else {}
        if slug in variants:
            return scene, variants[slug]
    raise KeyError(f"unknown variant: {slug}")


def _character(doc, spec):
    name = spec.get("character") or next(iter(doc.get("characters", {})))
    return name, doc["characters"][name]


def compose_still(doc: dict, slug: str) -> dict:
    """Merges attributes ← outfit ← variant into one generation prompt."""
    _, spec = _find_variant(doc, slug)
    char_name, char = _character(doc, spec)
    attrs = {k: v for k, v in char["attributes"].items() if k != "negatives"}
    merged = {**attrs, **doc["outfits"][spec["outfit"]]}
    held = spec.get("held")
    if held is not None:
        merged["carried"] = ", ".join(doc["props"][p] for p in held)
    expression = spec.get("expression", merged.get("expression"))
    merged.pop("expression", None)

    parts = [doc["style"], char["backdrop"]]
    parts += [f"{k}: {v}" for k, v in merged.items()
              if isinstance(v, str) and v and v != "nothing"]
    parts.append(f"pose: {spec['pose']}")
    if expression:
        parts.append(f"expression: {expression}")
    parts += [doc["effects"][e] for e in spec.get("effects", [])]
    return {
        "prompt": ". ".join(p for p in parts if p),
        "negative": ", ".join(
            char["attributes"].get("negatives", [])),
        "character": char_name,
    }


def compose_plate(doc: dict, slug: str) -> dict:
    """Merges place ← time ← extra into one background prompt."""
    spec = doc["plates"][slug]
    place = doc["places"][spec["place"]]
    time_ = doc["times"][spec["time"]]
    parts = [doc["style"], place["pro"], time_["pro"], spec.get("extra")]
    return {
        "prompt": ". ".join(str(p) for p in parts if p),
        "negative": ", ".join(place.get("con", []) + time_.get("con", [])),
    }


def _prompts_sheet(doc: dict) -> str:
    lines = ["# Character pose stills (one character, blank backdrop)",
             ""]
    for scene in doc["scenes"]:
        lines.append(f"## {scene.get('title', '<untitled>')}")
        lines.append("")
        if scene.get("plates"):
            lines.append("Backgrounds shot alongside: "
                         + ", ".join(f"`{p}`" for p in scene["plates"]))
            lines.append("")
        for slug in scene.get("variants", {}):
            composed = compose_still(doc, slug)
            lines += [f"### {slug}",
                      "",
                      f"**Prompt:** {composed['prompt']}",
                      f"**Negative:** {composed['negative']}",
                      ""]
    lines += ["# Background plates", ""]
    for slug in doc["plates"]:
        composed = compose_plate(doc, slug)
        lines += [f"### {slug}",
                  "",
                  f"**Prompt:** {composed['prompt']}",
                  f"**Negative:** {composed['negative']}",
                  ""]
    return "\n".join(lines)


def emit(doc: dict) -> str:
    ok, findings = validate(doc)
    if not ok:
        raise ValueError("breakdown is invalid:\n" + "\n".join(findings))
    return _prompts_sheet(doc)


def main(argv=None):
    import argparse

    import sys

    parser = argparse.ArgumentParser(
        description="Validate a breakdown yaml and emit the derived "
                    "generation prompt sheet.")
    parser.add_argument("breakdown", help="path to the breakdown yaml")
    parser.add_argument("--out", help="path for the derived prompt sheet "
                                      "(default: alongside the breakdown, "
                                      "_prompts.md suffix)")
    args = parser.parse_args(argv)
    try:
        doc = load(args.breakdown)
    except yaml.YAMLError as exc:
        print(f"yaml error: {exc}", file=sys.stderr)
        return 1
    ok, findings = validate(doc)
    if not ok:
        print("breakdown is invalid:", file=sys.stderr)
        print("\n".join(f"  - {f}" for f in findings), file=sys.stderr)
        return 1
    out = Path(args.out) if args.out else \
        Path(args.breakdown).with_name(
            Path(args.breakdown).stem + "_prompts.md")
    out.write_text(emit(doc), encoding="utf-8")
    print(f"valid — derived prompt sheet written to {out}")
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
