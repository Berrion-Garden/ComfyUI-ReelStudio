---
name: reel-yaml-schema
description: The reel.yaml contract — meta, aliases, stills, scene layers (video/sound_effects/music/post), anchor refs, frames. Load before reading or editing reel.yaml.
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
- `stills` — named anchor images resolved into `meta.still_dir` with a
  `_.png` suffix appended (`opening: qwen_image_2_1_00008` →
  `still_dir/qwen_image_2_1_00008_.png`).
- `flags` — `skip_music: true` compiles video + sound effects only.
- `scenes` — ordered list; `next:` slugs MUST agree with list order; the last
  scene ends the chain with `next: null`.

## Scene layers

- `video` — `mode` (`i2v` image-to-video, `fl2v` first+last, `t2v` text),
  `first`/`last` anchor refs, `description` (H3-Context-IR — see
  h3-prompting), optional `negative`.
- `sound_effects` — `soundscape` prose, baked INTO the clip by H3. Optional
  `bell: true` + `bell_at` (seconds into the scene) for the synthesized
  3-strike school bell.
- `music` — dict `{name, caption, gain?}` anchors a Music 3 segment at this
  scene; it runs until the next anchored scene or reel end. `music: none`
  keeps the previous segment playing. Names must be unique.
- `post.freeze` — motion until `at_s`, white impact flash `flash_s`, then a
  graded slow-push-in freeze. `grade` holds saturation/contrast/brightness/
  vignette; `names` holds drawtext credit data. H3 NEVER renders text —
  credits live here.
- `frames` — per-scene generation length. Length is GENERATED, never cut.
  Off the 17n+5 grid works but produces a validation warning.

## Anchor refs (`first`/`last`)

- `prev_last` — last frame of the previous scene's deliverable (junction
  mechanism; see junction-doctrine).
- `still:<name>` — entry in `stills:`.
- absolute path — literal.
- `null` — free ending (i2v) or no pin.
