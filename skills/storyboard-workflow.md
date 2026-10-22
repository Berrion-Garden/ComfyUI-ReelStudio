---
name: storyboard-workflow
description: The production lifecycle — build the checkpoint narrative with the operator, then derive character/location YAML from prompts and images. Load before any narrative or storyboard work.
---
# Storyboard workflow

The narrative is the base of everything. `storyboard.yaml` (studio root,
read it with `get_narrative`) owns the checkpoint-by-checkpoint story:
`style:` + ordered `acts:`, each with its music/sync note and its
`checkpoints:` — every checkpoint `{title, text, characters, locations}`.
The Storyboard stage view renders exactly this, plus the digested
character/location/scene YAML of the current reel.yaml.

## Building the narrative

- Work it out WITH the operator: propose acts and checkpoints, ask what a
  beat should show, then write it in. The operator sees every word —
  `text` is prose for humans AND the seed of the shot prompts.
- Mirror their material: a pasted prompt or scene list becomes
  checkpoints verbatim (titled, ordered); a dropped image becomes a
  checkpoint's text described through `view_image`.
- `characters`/`locations` on a checkpoint are SLUG LISTS — name exactly
  the entities the beat shows. They render as links into the YAML views;
  a slug that has no block yet is a TODO you can see.
- Edit with `update_narrative`: read → edit → submit the complete
  document. The whole update is rejected on structural errors; the error
  names the offending checkpoint.

## Deriving the YAML

Character and location blocks in reel.yaml are derived from the narrative
plus the operator's prompts/images — through `update_yaml`, never by
hand-editing pool images:

- **Character from a prompt** — extract durable identity anchors into
  `attributes` (one key per trait: hair, skin, eyes, outfit…; `negatives`
  are bare concept words only). Keep it MINIMAL: every prompt splices
  these in.
- **Character from an image** — `view_image` first, then pull the anchors
  you actually see. Text feedback from the operator overwrites pulled
  info; the image itself is provenance (`ref`), never a model input.
- **Location** — one `pro:` paragraph that fixes EXT/INT, time of day,
  weather, and the one or two details that make the place recognizable.
  `con:` only what must be subtracted.
- After writing blocks, say what changed and which scenes it touches —
  editing a block marks its scenes stale via the collapse.
