---
name: reel-lifecycle
description: The reel pipeline lifecycle — the one-way stages from original
  script to delivered animations, the judgment gates between them, and the
  review discipline at each gate. Use when planning reel work, judging
  renders, or auditing script fidelity.
always: true
---
# Reel lifecycle — stages and gates

The pipeline is a one-way flow from an original prompt to delivered
animations. Each stage consumes the previous stage's artifacts; the yaml
schema (`reel-yaml-schema.md`) is the contract between them. Nothing skips a
gate, nothing is added that is not in the script.

## Stages

1. **Breakdown** — from the original script into three leaf trees, all in
   `reel.yaml`, all schema-validated:
   - characters → `variants` (one pose/position leaf per checkpoint)
   - locations → sub-location plates per scene
   - `shots:` → the action description per checkpoint (the between-anchors
     action, not the end state)
2. **Combination review** — every (character × position × location × action)
   combination is checked: does it make sense, and does it follow the
   original script? Nothing beyond the script is created.
3. **Leaf generation** — one image per position/sub-location leaf, rendered
   in triplicate (`sheet … --copies=3`) with the appropriate anchors.
   Judgment tags the pick `pose:<slug>` in `assets.yaml`.
4. **Merge** — pose + plate merged (`shot <leaf>`), also in triplicate.
   Judgment tags the pick `shot:<slug>` + `verified` + `still:<anchor>`.
5. **Scene triples** — `reel.py collapse` emits the per-scene contract:
   **start anchor → end anchor + action description**, plus frames/music.
   Every scene has exactly one triple; a scene without both anchors is not
   renderable.
6. **Triple review** — each triple is checked against the original script:
   the characters in the scene are the scripted ones, the action between the
   anchors is the scripted action, the full flow of the script is covered,
   and nothing is added.
7. **Animation** — per-scene i2v renders from the triple, then review of the
   clips against the same criteria (sense, script fidelity, nothing added).
8. **Assemble** — concat + mix + any scene `post:` overlays into the
   deliverable in `meta.reel_dir`.

## Gates

A stage's outputs are born `non-verified`; a gate is a judgment recorded in
`assets.yaml` labels (the only registry). `reel.py review` prints what is
pending at each gate: unpicked leaves, unverified merges, scenes whose triple
does not resolve, and the triples themselves for script-fidelity reading.

Failures stay on disk untagged — a render is never deleted, only outranked by
a fresh round. A re-round changes the leaf text or seed; the old files keep
their birth labels.
