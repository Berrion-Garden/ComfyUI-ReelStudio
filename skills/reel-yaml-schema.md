---
name: reel-yaml-schema
description: The reel.yaml contract — meta, aliases, characters, styles/locations, stills, scene layers (video/sound_effects/music/post), anchor refs, frames, the collapse staleness. Load before reading or editing reel.yaml.
always: true
---
# reel.yaml schema

One scene = one narrative chunk with three editable layers. The file is the
single source of truth; code never holds a second copy.

## Structure

- `meta` — `comfy` (ComfyUI URL), `fps` (24), `frames` (default scene length,
  e.g. 107 = 17×6+5), `width`/`height`, `steps`, `still_dir` (Qwen stills
  output), `reel_dir` (render outputs, lives under ComfyUI's output dir),
  `final` (output path of the assembled mix), `work` (scratch).
- `aliases` — character/style shorthand spliced into descriptions with
  `{name}`. Define once, reference everywhere; never inline a character
  description twice.
- `styles` — map of named look blocks `{pro, con}` (see film-grammar for the
  vocabulary); `style:` names the ACTIVE one. The active style's `pro` is
  prepended to EVERY video prompt and its `con` merged into every negative —
  so one edit there cascades staleness to the whole reel. Keep only what
  should be universally consistent here (aesthetic, grade, rendering rules).
- `locations` — map of slug → `{pro, con}` shared location notes; a scene
  references one with `location: <slug>` and only those scenes get the
  injection (consistent location across a subset, one edit). EXT/INT, D/N,
  time-of-day and weather belong here.
- `characters` — map of slug → character reference block; drives
  `generate kind=sheet` (CHARACTER images — stills/refs/poses, never scenes).
  TEXT-driven: the pool images are the SOURCE of `attributes` (pulled out
  once, then corrected by the operator's feedback — feedback overwrites
  pulled info, never the reverse) and are NEVER fed to the model as image
  inputs — feeding them pins every output to the image and kills variety.
  `attributes` — THE identity anchors as named keys (hair, skin, eyes,
  bandages, accessories, outfit), joined in yaml order into every prompt;
  edit ONE key to change one trait, never restate a trait in two places.
  `ref` — provenance only: which pool image the description was pulled
  from; not a model input. `backdrop` — the blank studio background text;
  reference stills are ALWAYS one character on a blank backdrop.
  `variants` — one directive per still: a pose, a framing (full-body or
  close-up), or an attribute variance (hair, clothes, style). `negatives`
  (inside attributes) — BARE CONCEPT WORDS ONLY, the engine SUBTRACTS each
  named concept ("undercut, bandaged mouth" removes those things); "no X"
  wording would instead condition X into the image — forbidden here. The
  value rides the negative input (informative at cfg 1 — the positive text
  must also omit the concept).
  The character block is an inheritance TREE:
  `attributes` (Base) → `layers` (named uniform/scene edits, e.g.
  `layers.archery` = "Archery Uniform Amun": outfit + magic canon) →
  `variants` (leaves). Every variant is a MAP — the string pose form is
  retired (the validator rejects it): `slug` (unique across the tree,
  names the pose pool), `pose` (required), optional `layer: <name>`
  attaching a mid-node; any non-control key replaces the same-named
  attribute for THIS still, everything absent inherits. Variant seeds are
  unique across the tree (the validator rejects dupes).
  YAML anchors + merge keys keep a leaf family single-source
  (`- &archery_anchor {…}` then `{<<: *archery_anchor, seed: 915000}`).
  CONTROL KEYS (`pose`, `seed`, `layer`, `negatives`) never reach the
  prompt text — a seed number in the text conditions garbage. A variant
  `seed:` is used VERBATIM for that render (the seed ladder
  `base + i*7919` applies only to variants without one); per-image proven
  via the embedded PNG metadata (`Image.info['prompt']` → KSampler seed +
  TextEncodeQwenImage21 text).
  `seeds` —
  seeds of APPROVED stills, recorded automatically on ✓ approval; the next
  run starts its seed ladder from what worked. Style comes from the active
  `styles:` block, never from the character. Still outputs are born
  `non-verified` in the `characters/<slug>/` pool. A legacy `description:`
  string still works (joined whole) but attributes is the interface.
- `stills` — the anchor-NAME registry only: every entry must be null
  (the validator rejects path values). The pick for a name lives in
  `assets.yaml` tagged `still:<name>`; the resolver also accepts the
  `<name>_.png` render convention, then a unique pool slug match. New
  picks land with the `anchor_still` tool, never a path entry.
- `shots` — Qwen-Image-2.1 per-shot anchor-still recipes (`reel.py shot
  <name>` or `generate kind=image_edit name=<name>`): `characters` (slugs —
  each resolves to the sheet tagged `ref` in `assets.yaml`; a dict
  `{slug: Amun, ref: <label>}` picks a different approved body by its label
  instead — the archery base for the kyudo shots), `background`
  (a `backgrounds/` plate), `description` (what happens). Every run renders
  10 seed/prompt variants into the stills dir, born `non-verified`; anchor
  the pick with `anchor_still` (tags it `still:<name>`, sets the scene ref).
- `flags` — `skip_music: true` compiles video + sound effects only.
- `audio` — top-level array of REAL-FILE overlay tracks (what the production
  mix actually uses). Each entry is an absolute timestamp note: `file` (path
  to the track), `at` (video-time start, seconds), `seek` (source offset into
  the track), `gain`, and `fades` (sorted `[second, volume]` keyframes in
  video time — the last keyframe ends the track; otherwise it runs to the
  reel end). Replaces the old per-scene `music_2`.
- `sfx_volume` — volume automation for the sound baked into the renders:
  absolute video-time `[second, volume]` keyframes, linear between points,
  held before the first / after the last.
- `scenes` — ordered list; `next:` slugs MUST agree with list order; the last
  scene ends the chain with `next: null`.

## Scene layers

- `location` — optional slug into `locations:`; injected pro/con for this
  scene only.
- `video` — `mode` (only `i2v` remains; the graph stages first+last when
  both anchors resolve, so the old fl2v/t2v names are retired),
  `first`/`last` anchor refs, `description` (H3-Context-IR — see
  h3-prompting), optional `negative`. The description holds only what is
  specific to this shot: action, blocking, shot size, camera move.
- `sound_effects` — `soundscape` prose, baked INTO the clip by H3. Optional
  `bell: <slug>` + `bell_at` (seconds into the scene): the slug names an
  `sfx/` asset, played as a one-shot at that moment (there is no synth
  fallback — an unknown slug is a plan error).
- `music` — dict `{name, caption, gain?}` anchors a GENERATED Music 3 segment
  at this scene; it runs until the next anchored scene or reel end.
  `music: none` keeps the previous segment playing. Names must be unique.
  Real audio files live in the top-level `audio:` array, not here.
- `post.freeze` — motion until `at_s`, white impact flash `flash_s`, then a
  graded slow-push-in freeze. `grade` holds saturation/contrast/brightness/
  vignette; `names` holds drawtext credit data. H3 NEVER renders text —
  credits live here.
- `frames` — per-scene generation length. Length is GENERATED, never cut.
  Off the 17n+5 grid works but produces a validation warning.

## Anchor refs (`first`/`last`)

- `prev_last` — last frame of the previous scene's deliverable (junction
  mechanism; see junction-doctrine).
- `still:<name>` — the file tagged `still:<name>` in assets.yaml (the pick;
  a legacy `stills:` path entry also resolves). Ambiguous without the label —
  anchor picks with the `anchor_still` tool.
- absolute path — literal.
- `null` — free ending (i2v) or no pin.

## Staleness: the collapse

`reel.py collapse` merges the yaml into each scene's FINAL generation input —
prompt text, negative (scene + style con + location con, term-deduped),
resolved anchors with file-content hashes, frames, size. The studio caches
that artifact in the manifest at render time; a scene is stale exactly when
the fresh collapse differs from the cached one. That is why editing the
active style, a location, a still file or an upstream render all mark the
right scenes for re-render automatically — there is no second staleness
mechanism to keep in sync.
