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
_SCENE_PROVENANCE_HEADER = (
    "# DERIVED from the Amunrekh breakdown (the creative canon):\n"
    "#   {breakdown}\n"
    "# Regenerate: .venv/bin/python -m reelstudio.storyboard_doc "
    "{breakdown} --emit-scene <out>\n"
    "# Production state is NOT included: `seeds`, the reference-leaf "
    "family, `stills`,\n"
    "# `shots`, `scenes`. Graft `characters` and `locations`, keeping your "
    "seeds by slug.\n"
    "# Verify after grafting: --check <scene reel.yaml>\n")


class StrictLoader(yaml.SafeLoader):
    """SafeLoader that raises on duplicate mapping keys — a silent overwrite
    is a single-source-of-truth bug the parser must not hide.

    Merge handling is done HERE, not delegated to PyYAML's flatten (whose
    inherited-pair ordering differs between block and flow mappings):
    explicit keys are collected first (explicit-explicit duplicates RAISE),
    then inherited keys (`<<: *anchor`) graft only where not explicitly
    present — the spec's explicit-overrides-inherited, independent of pair
    order. A key that is BOTH explicit and inherited is an override, never
    a duplicate."""

    MERGE_TAG = "tag:yaml.org,2002:merge"

    def construct_mapping(self, node, deep=False):
        explicit = {}         # constructed key -> value node
        explicit_order = []   # [(key, value node)] in document order
        inherited = []        # [(key, value node)] from merge anchors
        for key_node, value_node in node.value:
            if key_node.tag == self.MERGE_TAG:
                self._collect_merge(value_node, inherited, deep)
                continue
            key = self._construct_key(key_node)
            if key in explicit:
                raise yaml.constructor.ConstructorError(
                    None, None, f"duplicate key {key!r}", key_node.start_mark)
            explicit[key] = value_node
            explicit_order.append((key, value_node))
        mapping = {}
        for key, value_node in explicit_order:
            mapping[key] = self.construct_object(value_node, deep=deep)
        for key, value_node in inherited:
            if key not in mapping:  # explicit overrides inherited
                mapping[key] = self.construct_object(value_node, deep=deep)
        return mapping

    def _construct_key(self, key_node):
        key = self.construct_object(key_node, deep=True)
        try:
            hash(key)
        except TypeError as exc:
            raise yaml.constructor.ConstructorError(
                None, None, "unhashable key", key_node.start_mark) \
                from exc
        return key

    def _collect_merge(self, value_node, inherited, deep):
        """One merge contribution: a mapping, or a sequence of mappings
        (earlier maps win). Chains (`<<` inside an anchor) recurse."""
        if isinstance(value_node, yaml.MappingNode):
            pairs = value_node.value
        else:  # a list of mappings to merge
            pairs = [pair for m in value_node.value for pair in m.value]
        for key_node, value_node in pairs:
            if key_node.tag == self.MERGE_TAG:
                self._collect_merge(value_node, inherited, deep)
                continue
            inherited.append((self._construct_key(key_node), value_node))


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


def compose_location_pro(doc: dict, slug: str) -> str:
    """Plate pro text as the scene yaml's `locations.<slug>.pro`: place +
    time (+ extra), each sentence-capped, con lists dropped (the negative
    channel is inert at cfg 1.0)."""
    spec = doc["plates"][slug]
    parts = [doc["places"][spec["place"]]["pro"],
             doc["times"][spec["time"]]["pro"]]
    if spec.get("extra"):
        parts.append(spec["extra"])
    return ". ".join(_sentence(p) for p in parts if p)


def _sentence(text: str) -> str:
    return text[:1].upper() + text[1:] if text else text


def compose_leaf(doc: dict, slug: str) -> dict:
    """One scene-yaml leaf: control slugs + the composed prompt-text keys.
    No `seed` — production state the seat grafts by slug."""
    _, spec = _find_variant(doc, slug)
    outfit = doc["outfits"][spec["outfit"]]
    leaf = {"slug": slug, "layer": spec["outfit"], "pose": spec["pose"]}
    if "expression" in spec:
        leaf["expression"] = spec["expression"]
    if spec.get("held"):
        leaf["held"] = ", ".join(doc["props"][p] for p in spec["held"])
    if spec.get("effects"):
        leaf["effects"] = "; ".join(doc["effects"][e] for e in spec["effects"])
    return leaf


def compose_attributes(doc: dict, char_name: str) -> dict:
    attrs = dict(doc["characters"][char_name]["attributes"])
    if isinstance(attrs.get("negatives"), list):
        attrs["negatives"] = ", ".join(attrs["negatives"])
    return attrs


def compose_layers(doc: dict) -> dict:
    return {slug: {k: v for k, v in outfit.items() if v != "nothing"}
            for slug, outfit in doc["outfits"].items()}


def emit_scene_yaml(doc: dict, character: str | None = None) -> dict:
    """The derived `characters` + `locations` blocks for the production
    scene yaml. Production state (seeds, the reference-leaf family,
    stills, shots, scenes) is NOT included — the seat grafts the blocks
    and keeps its seeds by slug."""
    ok, findings = validate(doc)
    if not ok:
        raise ValueError("breakdown is invalid:\n" + "\n".join(findings))
    char_name = character or next(iter(doc["characters"]))
    char = doc["characters"][char_name]
    variants = [compose_leaf(doc, slug)
                for scene in doc["scenes"]
                for slug in scene.get("variants", {})]
    block = {
        "backdrop": char["backdrop"],
        "attributes": compose_attributes(doc, char_name),
        "layers": compose_layers(doc),
        "variants": variants,
    }
    locations = {slug: {"pro": compose_location_pro(doc, slug)}
                 for slug in doc["plates"]}
    return {"characters": {char_name: block}, "locations": locations}


def check_scene_yaml(doc: dict, scene, character: str | None = None) -> tuple:
    """Round-trip: the scene yaml's derived blocks must equal fresh composer
    output. Any divergence is a finding — the scene yaml is STALE against
    the canon. Production state (seeds, reference leaves, meta, styles,
    stills, shots, scenes) is ignored."""
    expected = emit_scene_yaml(doc, character)
    char_name = character or next(iter(doc["characters"]))
    if isinstance(scene, (str, Path)):
        scene = yaml.load(Path(scene).read_text(encoding="utf-8"),
                          Loader=StrictLoader)
    findings: list = []
    scene_characters = scene.get("characters", {})
    if char_name not in scene_characters:
        findings.append(f"scene yaml has no character {char_name!r}")
        return False, findings
    block = scene_characters[char_name]
    exp_block = expected["characters"][char_name]

    if block.get("backdrop") != exp_block["backdrop"]:
        findings.append(
            f"backdrop drift: breakdown says {exp_block['backdrop']!r}; "
            f"scene yaml has {block.get('backdrop')!r}")

    scene_attrs = block.get("attributes", {})
    for key, val in exp_block["attributes"].items():
        scene_val = scene_attrs.get(key)
        if key == "negatives" and isinstance(scene_val, list):
            scene_val = ", ".join(scene_val)
        if scene_val != val:
            findings.append(
                f"attribute drift on '{key}': breakdown says {val!r}; "
                f"scene yaml has {scene_val!r}")
    for key in set(scene_attrs) - set(exp_block["attributes"]):
        findings.append(f"attribute '{key}' in scene yaml but not in the "
                        "breakdown")

    scene_layers = block.get("layers", {})
    for slug, layer in exp_block["layers"].items():
        if slug not in scene_layers:
            findings.append(f"layer missing: {slug} (in the breakdown, "
                            "absent from the scene yaml)")
            continue
        for key, val in layer.items():
            if scene_layers[slug].get(key) != val:
                findings.append(
                    f"layer drift on '{slug}.{key}': breakdown says "
                    f"{val!r}; scene yaml has "
                    f"{scene_layers[slug].get(key)!r}")
    for slug in set(scene_layers) - set(exp_block["layers"]):
        findings.append(f"unknown layer '{slug}' — not in the breakdown")

    by_slug = {leaf.get("slug"): leaf for leaf in
               block.get("variants", []) if isinstance(leaf, dict)}
    expected_leaves = {leaf["slug"]: leaf for leaf in
                       exp_block["variants"]}
    for slug, leaf in expected_leaves.items():
        scene_leaf = by_slug.get(slug)
        if scene_leaf is None:
            findings.append(f"leaf missing: {slug} (in the breakdown, "
                            "absent from the scene yaml)")
            continue
        for key in ("layer", "pose", "expression", "held", "effects"):
            exp_val = leaf.get(key)
            scene_val = scene_leaf.get(key)
            if exp_val != scene_val:
                findings.append(
                    f"leaf drift on '{slug}.{key}': breakdown says "
                    f"{exp_val!r}; scene yaml has {scene_val!r}")
    for slug, scene_leaf in by_slug.items():
        if slug in expected_leaves:
            extra = set(scene_leaf) - {"slug", "layer", "pose", "expression",
                                       "held", "effects", "seed"}
            if extra:
                findings.append(f"leaf '{slug}': unknown keys {sorted(extra)}"
                                " — allowed: slug, layer, pose, expression, "
                                "held, effects, seed")

    scene_locations = scene.get("locations", {})
    for slug, spec in expected["locations"].items():
        if slug not in scene_locations:
            findings.append(f"location missing: {slug} (in the breakdown, "
                            "absent from the scene yaml)")
        elif scene_locations[slug].get("pro") != spec["pro"]:
            findings.append(
                f"location drift on '{slug}': breakdown says "
                f"{spec['pro']!r}; scene yaml has "
                f"{scene_locations[slug].get('pro')!r}")
    for slug in set(scene_locations) - set(expected["locations"]):
        findings.append(f"unknown location '{slug}' — not in the breakdown")

    return not findings, findings


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
    parser.add_argument("--check", help="scene reel.yaml: round-trip its "
                                        "derived blocks against the "
                                        "breakdown and report staleness")
    parser.add_argument("--emit-scene", help="write the derived "
                                             "characters/locations blocks "
                                             "(for grafting into the scene "
                                             "yaml) to this path")
    args = parser.parse_args(argv)
    try:
        doc = load(args.breakdown)
    except yaml.YAMLError as exc:
        print(f"yaml error: {exc}", file=sys.stderr)
        return 1
    if args.check:
        ok, findings = check_scene_yaml(doc, args.check)
        if not ok:
            print(f"scene yaml is stale against the breakdown "
                  f"({len(findings)} findings):", file=sys.stderr)
            print("\n".join(f"  - {f}" for f in findings), file=sys.stderr)
            return 1
        print(f"scene yaml matches the breakdown — no drift")
        return 0
    ok, findings = validate(doc)
    if not ok:
        print("breakdown is invalid:", file=sys.stderr)
        print("\n".join(f"  - {f}" for f in findings), file=sys.stderr)
        return 1
    if args.emit_scene:
        out = Path(args.emit_scene)
        out.write_text(_SCENE_PROVENANCE_HEADER.format(
            breakdown=Path(args.breakdown).resolve()) + yaml.dump(
                emit_scene_yaml(doc), Dumper=yaml.SafeDumper,
                sort_keys=False, allow_unicode=True, width=76),
            encoding="utf-8")
        print(f"derived scene blocks written to {out}")
        return 0
    out = Path(args.out) if args.out else \
        Path(args.breakdown).with_name(
            Path(args.breakdown).stem + "_prompts.md")
    out.write_text(emit(doc), encoding="utf-8")
    print(f"valid — derived prompt sheet written to {out}")
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
