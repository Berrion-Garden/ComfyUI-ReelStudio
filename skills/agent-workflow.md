---
name: agent-workflow
description: The Reel Studio agent tool protocol — get_project staleness reading, validate-gated update_yaml, the six generate kinds, get_assets, currently_selected, view_image (you are visual), update_asset_labels, get_provenance, adopt_renders, get_skill, and what to report. Always on; the reference for every tool call.
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
  being the `primary` they are looking at. Their PICTURES are delivered to
  you right after the result — referencing the selection is looking at it.
  The operator may also paste
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
  - `sheet` — CHARACTER images (stills, refs, poses — never scenes or
    video). Anime stills of one character, one pose/directive, BLANK
    backdrop, per image. Driven ENTIRELY by the yaml `characters:` block
    (see reel-yaml-schema: attributes/backdrop/variants/seeds/negatives) —
    art direction goes into those KEYS first, then queue the run; every
    still is born `non-verified` with `posed`. The full contract lives in
    reel-yaml-schema and asset-library — do not restate it here.
  - `still` — render a background/location plate from a `locations:` entry
    (`slug:`) — 10 seed/prompt variants into `backgrounds/<location>/`.
  - `image_edit` — render a `shots:` entry's anchor stills (`name:`) —
    character refs + background plate, strict identity/scene roles, 10
    variants into the stills dir. The operator picks (and verifies) in the
    asset view; anchor the pick with `anchor_still` (tag + scene ref in one
    call).
- `get_status` reports queued/running/done/error jobs. Renders are minutes
  per scene on the GPU node; report what was queued, do not poll silently.
- `get_provenance` is the claw-back: one generated file's job id, its queued
  request (kind/target/args), the H3 noise seed for videos, and — for images
  — the exact prompt, negative prompt, seed, steps and models ComfyUI
  embedded in the PNG. Use it when the operator asks "how was this made?"
  or wants a regeneration from the same seed. Every generated file carries
  its `job:<id>` label (assets.yaml) or manifest `job` field automatically;
  the journal lives in the scene's `.studio/jobs.jsonl`.
- `view_image` is your eyes: you are visual. Call it for any library image
  and it is delivered with the next message. LOOK
  before judging anything visual — a generated plate's composition, whether
  a sheet is a clean multi-view, whether a pick matches its `shot:`
  description — and describe what you actually see, never what the filename
  suggests. The gateway flattens tool results to text, so pictures ride the
  next user turn; if you don't see one, call view_image again. The operator
  can also force their selection's picture into a message with the 📎-row
  toggle — that one arrives without any tool call.
- `adopt_renders` declares the CURRENT deliverables current so staleness
  starts from truth — explicit operator instruction only (their ✓ adopt on
  a timeline thumbnail does one scene).
- `get_studio` is the scene registry (every studio scene with its character
  and location pools, the current one). Cross-scene work starts here — the
  operator's File menu creates scenes; you cannot.
- `import_assets` copies a character or location pool from another scene
  into the current one — into a new pool or merged into an existing one
  (`as`); it never clobbers files and declared labels come along.
- `get_skill` loads an on-demand skill's full body (`film-grammar`,
  `junction-doctrine`, `asset-library`, `app-troubleshooting`). The system
  prompt carries the always-on skills (this workflow, reel-yaml-schema,
  h3-prompting) and the index of the rest — pull one when your task matches
  its description, e.g. film-grammar before writing shot notes, and
  app-troubleshooting when a job errors.

## The engine reads yaml vocabulary ONLY

Every generation prompt is composed from the reel's own yaml — character
`attributes`/`variants`/`backdrop`, the active `style` — and NOTHING else:
never an asset filename, never "like the <name> still", never "the ref04
look". A image model has no idea what those names mean: the phrase either
does nothing or conditions a wrong concept (a referenced "chin wrap" became
a mouth-eating mask for four rounds).

When the operator says "take X from still N": that is a TRANSLATION job —
`view_image` the named still, look at the quality they mean, and write
those words into the right `characters.<slug>` key with `update_yaml`
BEFORE queueing the run. The yaml is the merge point of all approvals;
the prompt is yaml-only vocabulary.

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
   importing pools from another scene). You cannot create one; `get_studio`
   shows what exists.
2. **Places** — add the location to `locations:` (update_yaml), then
   `generate kind=still` → 10 plates in `backgrounds/<location>/` → one gets
   tagged
   `ref` (the operator ✓-picks, or tags it themselves; you set the label
   with `update_asset_labels` when they say which).
3. **Cast** — the operator drops reference images into the Characters section
   (+ button or drag-and-drop; they label `char:<pool>`), then
   `generate kind=sheet` → 10 reference stills (one character, one pose,
   blank backdrop) → one gets tagged `ref`
   (same as above).
4. **Shot anchors** — add a `shots:` entry (characters + background +
   description), `generate kind=image_edit` → 10 variants → the operator
   picks one → anchor it with `anchor_still`.
5. **Video** — add the `scenes:` entry (reel-yaml-schema + h3-prompting),
   `generate kind=scene` for it.
6. **Verify** — `get_project`; the operator ✓-adopts each finished scene's
   render on its timeline thumbnail.

Each generate step is 10 variants, ~30–60s/image on the GPU — queue it, say
so, and let the operator review while it runs. You can look at the variants
yourself with view_image and recommend a pick; the operator confirms.

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
5. An explicitly requested generation is QUEUED IN THE SAME TURN. "Generate
   10" means `generate` now, then report what was queued — never a
   "shall I…?" question for what was just asked. Questions are for real
   ambiguity, not for proceeding.
6. The operator's words map to kinds: "images/stills/refs/pictures of a
   character" → `sheet`; "background/plate" → `still`; "scene still/shot" →
   `image_edit`; "render/animate/video" → `scene`. Character images are
   NEVER scenes, and a character request must not be answered with YAML
   video edits.
7. Anchoring the selection ("make this the first/last scene anchor"):
   `currently_selected` → `anchor_still` (path, scene_id, anchor; the tool
   tags the file `still:<name>` and sets `video.first:`/`video.last:`) →
   re-render the affected scene. That is the whole
   recipe — no questions between steps when the operator named the anchor
   and the scene.
8. Operator feedback about generated images LANDS IN THE YAML, then the
   run: write their words into the `characters.<slug>` keys that drive the
   generation (attributes/variants/backdrop) with `update_yaml`, then queue
   `generate kind=sheet`. Feedback is never just acknowledged in chat —
   the yaml is the single source of truth and the run proves it. When the
   operator names good variants (by number or seed), record those seeds
   into `characters.<slug>.seeds:` — the next run ladders from what worked.
   Exclusions go into `attributes.negatives` as BARE words — the negative
   channel SUBTRACTS those concepts; writing "no X" CONDITIONS X instead.
   NEVER delete or clear existing pool files when regenerating — a run
   ADDS files (fresh seed-and-timestamp names); approved/kept assets are
   untouchable. Clearing the pool happens only when the operator says so
   in words, after their picks are recorded.
