---
name: agent-workflow
description: The Reel Studio agent tool protocol — get_project staleness reading, validate-gated update_yaml, the six generate kinds, get_assets, currently_selected, update_asset_labels, get_provenance, adopt_renders, get_skill, and what to report. Always on; the reference for every tool call.
always: true
---
# Agent workflow

## The tools

- `get_project` is the read model: per-scene `stale`, `rendered`, `start_s`,
  `duration_s`, anchor kinds, plus music segments, overlays, the `stills` map
  (a `present: false` entry is a broken anchor — fix it or ask), alias names,
  the active `style` and `locations`, flags. Read it before and after every
  edit.
- `get_assets` is the derived library: character pose pools (`char:`/`pose:`),
  custom images, themes, audio, and `used_by` per still. Find anchor images by
  label here — never guess filenames (see asset-library).
- `currently_selected` is the request-scoped selection: every asset the
  operator picked in the studio (shift-click multi-selects), the last one
  being the `primary` they are looking at. The operator may also paste
  `asset:<path>` references — produced by an asset thumbnail's
  copy-reference menu — those paths match `get_assets` entries exactly.
- `update_yaml` replaces the WHOLE file and is validate-gated: one atomic edit
  per call. ALWAYS `get_yaml` first, edit that text, submit the complete file.
  On a validation error, fix the SAME text and retry — never re-read and start
  over. The result may carry `warnings` (e.g. off-grid frames): those are
  allowed; do not "fix" a working scene length because of one. It edits
  reel.yaml ONLY — library labels (assets.yaml) go through
  `update_asset_labels`.
- `update_asset_labels` adds/removes labels on one library asset: tag a pick
  `ref` (the tag `char_ref`/`plate_ref` resolve — what the next generation
  references), remove `non-verified` to keep a generated image, add `cond:`
  context. Derived labels (`char:`, `scene:`, `used_by`) are pipeline-owned;
  do not restate them.
- `generate` queues work on the single-GPU worker. Kinds:
  - `scene` — render videos. Pass `scene_ids` (queued upstream-first) or
    `stale: true` for every stale scene. NEVER render the whole chain when
    two scenes changed. EXCEPTION: an edit to the active `style:` block or
    `styles:` map is global — every scene's prompt changes, so the whole reel
    legitimately goes stale; say so and render the chain (or offer to).
    A `location:` edit cascades only to the scenes referencing it.
  - `music` — regenerate one anchored segment (`name:`).
  - `assemble` — the final production mix; only when the user asks for it.
  - `sheet` — generate a character's multi-view identity sheet (`slug:`) —
    10 seed/prompt variants into `characters/<slug>/`, collapsing the whole
    reference pool into one identity. The pool must already hold reference
    images; the operator uploads them (the + button or drag-and-drop on the
    Characters section — they land in `characters/<pool>/` and label
    `char:<pool>`). Born `non-verified`; the operator ✓-picks one and tags it
    `ref` — or you tag it yourself with `update_asset_labels` when they say
    which one.
  - `still` — render a background/location plate from a `locations:` entry
    (`slug:`) — 10 seed/prompt variants into `backgrounds/`.
  - `image_edit` — render a `shots:` entry's anchor stills (`name:`) —
    character refs + background plate, strict identity/scene roles, 10
    variants into the stills dir. The operator picks (and verifies) in the
    asset view; anchor the pick by adding it to `stills:`.
- `get_status` reports queued/running/done/error jobs. Renders are minutes
  per scene on the GPU node; report what was queued, do not poll silently.
- `get_provenance` is the claw-back: one generated file's job id, its queued
  request (kind/target/args), the H3 noise seed for videos, and — for images
  — the exact prompt, negative prompt, seed, steps and models ComfyUI
  embedded in the PNG. Use it when the operator asks "how was this made?"
  or wants a regeneration from the same seed. Every generated file carries
  its `job:<id>` label (assets.yaml) or manifest `job` field automatically;
  the journal lives in the scene's `.studio/jobs.jsonl`.
- `adopt_renders` declares the CURRENT deliverables current so staleness
  starts from truth — explicit operator instruction only (their ✓ adopt on
  a timeline thumbnail does one scene).
- `get_studio` is the scene registry (every studio scene, the current one,
  each scene's characters/backgrounds); `import_assets` copies pools and
  plates from another scene into the current one. Cross-scene work starts
  here — the operator's File menu creates scenes; you cannot.
- `get_skill` loads an on-demand skill's full body (`film-grammar`,
  `junction-doctrine`, `asset-library`, `app-troubleshooting`). The system
  prompt carries the always-on skills (this workflow, reel-yaml-schema,
  h3-prompting) and the index of the rest — pull one when your task matches
  its description, e.g. film-grammar before writing shot notes, and
  app-troubleshooting when a job errors.

## The loop for "change X"

1. `get_project` → find the affected scene(s) and who anchors on them
   (junction-doctrine decides the re-render set); `get_assets` when a new
   anchor image is needed.
2. `get_yaml` → `update_yaml` with the edit.
3. State what changed in one or two sentences.
4. `generate` with kind `scene` and exactly the affected set (offer first
   unless the user already asked for regeneration).
5. Report: edited scenes, re-rendered scenes (and WHY a downstream scene was
   included), what stayed untouched.

## Recipe: a new scene (both generation models)

Two "scene" levels, never confuse them: a **reel-scene** (a `scenes:` entry in
reel.yaml) and a **studio scene** (a directory under the studio wrapper,
File → New scene). The full pipeline for a fresh story chunk:

1. **Studio scene** — the operator does File → New scene (optionally
   importing characters/locations from another scene). You cannot create one;
   `get_studio` shows what exists, `import_assets` brings pools and plates
   over when asked.
2. **Places** — add the location to `locations:` (update_yaml), then
   `generate kind=still` → 10 plates in `backgrounds/` → one gets tagged
   `ref` (the operator ✓-picks, or tags it themselves; you set the label
   with `update_asset_labels` when they say which).
3. **Cast** — the operator drops reference images into the Characters section
   (+ button or drag-and-drop; they label `char:<pool>`), then
   `generate kind=sheet` → 10 identity sheets → one gets tagged `ref`
   (same as above).
4. **Shot anchors** — add a `shots:` entry (characters + background +
   description), `generate kind=image_edit` → 10 variants → the operator
   picks one → anchor it in `stills:`.
5. **Video** — add the `scenes:` entry (reel-yaml-schema + h3-prompting),
   `generate kind=scene` for it.
6. **Verify** — `get_project`; the operator ✓-adopts each finished scene's
   render on its timeline thumbnail.

Each generate step is 10 variants, ~30–60s/image on the GPU — queue it, say
so, and let the operator review while it runs.

## Rules

1. NEVER save YAML you have not validated mentally against reel-yaml-schema;
   a broken chain blocks the whole app until fixed.
2. NEVER invent scene ids or still names — they come from `get_project` and
   `get_assets`.
3. When the user asks "make it shorter", change `frames:` (generation length)
   and adjust the description; NEVER cut frames after the fact.
4. When an edit only touches the audio layers or `sound_effects:`, say so —
   sound changes still re-render the scene (H3 bakes the soundscape) but
   never cascade to still-anchored neighbours.
