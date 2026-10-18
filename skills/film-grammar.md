---
name: film-grammar
description: Condensed film vocabulary for style/location blocks and scene shot notes — every term pairs positive trigger words with negatives. Load before writing prompts.
---

# Film grammar for prompts

The yaml's `styles:`/`locations:` blocks and scene descriptions share one
vocabulary. Every term carries a **pro** (words to put in the prompt) and a
**con** (words for the negative) — the machinery merges the cons for you, so
scene notes only carry what is specific to that shot.

Where each category lives:

- **style** (reaches EVERY prompt): aesthetic, grade, rendering doctrine.
- **location** (reaches the scenes referencing it): EXT/INT, D/N, time of day,
  weather, environment details, its own color notes.
- **scene description** (one shot only): shot size, angle, camera move, the
  characters' actions — the actual narrative notes.

## Shot size (scene description)

| Term | Pro | Con |
|---|---|---|
| EWS | extreme wide shot, tiny figure against vast landscape | close-up, face fills the frame |
| WS / LS | wide shot, full environment visible | tight framing, cropped body |
| MWS / FS | full shot, head-to-toe in frame | extreme wide, distant speck |
| CS | cowboy shot, mid-thigh framing | full body, head-and-shoulders |
| MS | medium shot, waist-up | full body visible |
| MCU | medium close-up, chest-and-head framing | wide shot, small figure |
| CU | close-up on the face, frame-filling | wide shot, distant figure |
| ECU | extreme close-up, eye or detail fills the frame | wide shot, whole scene visible |

## Angle and blocking (scene description)

- eye-level (pro) / extreme perspective distortion (con)
- high angle, looking down (pro) / worm's-eye view (con) — and vice versa
- dutch angle, tilted horizon (pro) / level horizon (con)
- overhead, bird's-eye, top-down (pro) / ground-level view (con)
- OTS: over-the-shoulder, foreground shoulder framing the subject
- POV: point-of-view shot, first-person framing
- two-shot / clean single (only one subject in frame) / dirty single
  (other subject soft in the foreground)

## Camera (scene description)

- locked-off static camera, fixed frame (pro) — the H3 default — /
  camera shake, fast cuts, jerky motion (con)
- slow push-in / dolly-in; slow pull-back; gentle pan left/right; tilt up/down
- tracking shot following the subject; whip pan (pro: fast motion blur pan)
- rack focus, foreground-to-background focus pull
- handheld, slight organic sway (pro) / tripod-stable (con) — and vice versa

## Time, weather, environment (location block)

- EXT / INT: exterior or interior setting (pro names it: "outdoor city street",
  con excludes the complement: "indoor room" / "outdoors")
- D / N: day or night (pro: "bright afternoon", con: "dark night scene")
- golden hour, warm low sun / blue hour, cool twilight / magic hour
- overcast soft light (pro) / harsh shadows (con) — and vice versa
- rain, wet streets, reflections / snow, breath vapor / fog, mist
- day-for-night: moonlit blue palette (pro) / bright daylight (con)

## Color and grade (style block, usually)

- high saturation, vibrant flat colors / desaturated, muted palette — pick one
- warm palette, orange amber / cool palette, blue cyan
- high contrast, deep blacks / low contrast, flat washed light
- monochrome, black and white / full color (and vice versa)
- film grain, analog texture (pro) / clean digital, sterile smoothness (con)
- teal-and-orange complementary grade

## Lighting (style or location)

- high-key: bright even lighting, few shadows (pro) / low-key dark moody (con)
- low-key, dramatic chiaroscuro, deep shadow (pro) / flat even light (con)
- rim light, glowing edge outline on the subject
- backlight, subject against the light, lens flare
- silhouette, dark figure against bright background
- volumetric light, god rays through haze
- practicals: in-frame light sources (lamps, screens, lanterns)

## Lens and focus (scene description)

- wide-angle lens, exaggerated perspective / telephoto compression
- shallow depth of field, soft bokeh background / deep focus, everything sharp

## Production slate terms (map to MACHINERY, not prompt words)

- **PR** (print, the circled take): the adopted deliverable — recorded in the
  manifest as the render to keep.
- **NG** (no good): a failed render — an errored job, or a deliverable you are
  re-rendering; it never becomes the manifest's chosen path.
- **HOLD**: a backup render kept on disk (older `_00002_`-style outputs) but
  not the adopted one.
- **MOS** (shot without sound): a scene whose baked audio is suppressed —
  model it as no `sound_effects`, not as prompt words.
- **establishing shot / cutaway / insert / reaction shot**: scene-structure
  vocabulary — one job per scene, so structure IS the scene list.

## Writing rule

Scene notes say what HAPPENS and how the CAMERA sees it; never re-describe
the style or the location. If a scene note repeats words that belong in the
style or location block, move them there — one copy, one edit, every render
follows.
