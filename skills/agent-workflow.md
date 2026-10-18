---
name: agent-workflow
description: The Reel Studio agent tool protocol — get_project staleness reading, validate-gated update_yaml, the generate kinds (scene/music/assemble/still/image_edit, all wired), get_assets, currently_selected, get_skill, and what to report. Always on; the reference for every tool call.
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
  allowed; do not "fix" a working scene length because of one.
- `generate` queues work on the single-GPU worker. Kinds:
  - `scene` — render videos. Pass `scene_ids` (queued upstream-first) or
    `stale: true` for every stale scene. NEVER render the whole chain when
    two scenes changed. EXCEPTION: an edit to the active `style:` block or
    `styles:` map is global — every scene's prompt changes, so the whole reel
    legitimately goes stale; say so and render the chain (or offer to).
    A `location:` edit cascades only to the scenes referencing it.
  - `music` — regenerate one anchored segment (`name:`).
  - `assemble` — the final production mix; only when the user asks for it.
  - `still` — render a background/location plate from a `locations:` entry
    (`slug:`) — 10 seed/prompt variants into `backgrounds/`.
  - `image_edit` — render a `shots:` entry's anchor stills (`name:`) —
    character refs + background plate, strict identity/scene roles, 10
    variants into the stills dir. The operator picks (and verifies) in the
    asset view; anchor the pick by adding it to `stills:`.
- `get_status` reports queued/running/done/error jobs. Renders are minutes
  per scene on the GPU node; report what was queued, do not poll silently.
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
