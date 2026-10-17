---
name: h3-prompting
description: Writing video.description / negative / soundscape for MiniMax H3 — integrated_multimodal_description shape, what H3 bakes into audio, failure lessons. Load before writing or editing any scene prompt.
---
# H3 prompt writing

## Shape

A `video.description` is one structured block, not prose chat:

```
integrated_multimodal_description: [Shot 1] 2D anime, cel-shaded, clean bold line art.
<setting, held fixed>. <shot size and subject>. <action in order, concrete verbs>.
<camera: static/pan/push-in + amplitude>. <lighting>.
```

- State the style up front; pin the background as FIXED when it must not morph.
- Describe the LAST frame explicitly ("exactly like the final frame") when
  `last:` pins a still.
- `negative` is a comma list of concrete re-manifestation risks — not style
  words. "text, watermark, photorealistic, 3D rendering" always apply.

## Audio

- `sound_effects.soundscape` is baked into the clip: diegetic sounds only.
  Name the sounds, then constrain ("Wind, whooshes and impact sounds only.").
- Music is BANNED from clips: the renderer appends a non-diegetic_music ban
  automatically. Never put music in a soundscape; music is a `music:`
  segment mixed at assemble time.

## Rules

1. NEVER ask H3 to render text, logos or credits — it cannot; text belongs in
   `post.freeze.names`.
2. NEVER fight a re-manifesting object with negatives alone — change the
   imagery so the state is anchored (see junction-doctrine).
3. NEVER describe a character twice; use `{alias}`.
4. When a scene is shortened, tell the model the action completes within the
   shot ("the whole draw-and-lunge completes within the shot, brisk and
   relentless").
5. One action chain per scene; a scene that must show a landing, a reaction
   AND a departure is two scenes.
