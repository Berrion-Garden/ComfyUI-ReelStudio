# Reel Studio — plan

Date: 2026-10-16 · Rung: full · Source material: `llm_engine_management/anime_reel/` (reel.py + reel.yaml, session ses_ebc6f34d8ffevpTBt2ZhmQJPLR)

## Requirements

- FR-1: Load a `reel.yaml` workspace as the single source of truth; validate the `next:` chain, frame grid (17n+5), anchor refs, music and post config.
- FR-2: Display the chain as a horizontal timeline — one vertical slice per scene; anchor thumbnails on top, video deliverable below, audio rows under that (baked clip audio, anchored music segment).
- FR-3: Render any scene (or every stale scene) through the MiniMax H3 graph without leaving ComfyUI; freeze post applied where configured.
- FR-4: Mark scenes stale by config-hash + `prev_last` chain cascade; only changed scenes re-render.
- FR-5: Play the sequence seamlessly as though stitched, without concatenating files (dual-video preloading player).
- FR-6: Produce the final production mix (music bed, bell, concat, fade) only on explicit "Final production".
- FR-7: Chat agent (Berrion garden gateway) that reads/edits the YAML, reports what changed, and kicks off regeneration of affected scenes.
- FR-8: Well-designed pytest + Vitest suites covering model, graphs, assemble, agent and UI logic.

## Milestones

- M1 — BE project model + timeline + staleness + manifest + project routes — Self-contained
- M2 — BE Comfy client + H3 render + freeze post + render routes — blocked on M1
- M3 — BE assemble (music/bell/concat/mix) + assemble route — blocked on M1 (parallel with M2)
- M4 — BE agent (gateway client, tools, SSE chat) — blocked on M1 (parallel with M2/M3)
- M5 — FE app shell + timeline grid + thumbnails — blocked on M1
- M6 — FE player + staleness UI + render/assemble actions — blocked on M5, M2, M3
- M7 — FE chat panel wired to SSE — blocked on M5, M4
- M8 — Verification: full suites green, live smoke on the 5090 node — blocked on M1–M7

Critical path M1 → M2 → M6 → M8.

## Addendum — 2026-10-17: studio layout, asset library, multi-track timeline

Source: operator request after hosted deployment (Corel VideoStudio as UX reference).

- FR-9: Studio layout — player top-left with an asset viewer toggle, asset
  browser top-right, timeline beneath, chat at bottom as a standard LLM surface.
- FR-10: Timeline shows every audio track as spanning lanes: one per music
  segment (3 on the current reel), expanding across the scenes they cover, plus
  baked clip audio. A playhead overlay is clickable/draggable to scrub the
  preview to any point.
- FR-11: Asset library — top-level groups Images (Characters / Scenes / Custom),
  LORA/Theme, Audio. Navigable by keyboard. Selecting an image shows it in the
  player's asset viewer.
- FR-12: Programmatic image metadata — slugs and labels derived like the YAML:
  stills get `still:<name>` + `used_by:<scene>` from reel.yaml; character pools
  (`characters/<slug>/`) get `char:<slug>` + `pose:<file>`; declared labels in
  `assets.yaml` extend groups (images cross-group). Derived, never hand-copied;
  updating a pool gives the agent everything it needs to regenerate downstream.

Milestones:

- M9 — Studio layout: music artifact URLs (BE, small), layout reorder, asset
  viewer toggle in player, music lanes + scrub overlay, chat standard surface — blocked on M8
- M10 — Asset library: BE indexer + API (`/api/assets`, sandboxed file/thumb
  serving) + FE browser pane — blocked on M9
- M11 — Regeneration loop: agent tooling for pool-driven still regeneration and
  auto-tagging of newly generated images — blocked on M10 (labels land with M10)

---

## M12 addendum — Audio as first-class tracks + single-source-of-truth execution (2026-10-18)

Requirements:

- FR-13: `audio:` top-level array — real overlay tracks as absolute timestamp
  notes (`at` = video-time start, `seek`, `gain`, `fades`), replacing per-scene
  `music_2`. reel.yaml, reel.py and the app parsers change together.
- FR-14: Single source of truth — the app executes nothing: every
  render/music/assemble job is a subprocess call into `workspace/reel.py`
  (the only code that touches ComfyUI/ffmpeg). The app's own graph builders,
  comfy client, stub client and mix are deleted. The app records manifest
  entries after successful jobs so staleness stays truthful.
- FR-15: The preview chain mixes on the fly like the real mix: baked clip
  audio under the `sfx_volume` envelope (0.45 duck when music is in the mix),
  overlays start at `seek` with gain×fades envelopes, synth bell at `bell_at`
  (bell sample rendered by reel.py — one bell implementation), 1.2 s master
  fade; everything resyncs on play/pause/scrub.
- FR-16: The audio timeline is an audio graph: waveform per track, draggable
  volume anchors (the `fades` keyframes), add on click, delete on double-click;
  writes back to reel.yaml comment-preserving (ruamel.yaml). Lane players
  start at `seek`, never at 0.

Milestones:

- M12a — `audio:` schema + parsers (reel.yaml, reel.py `audio_tracks()`, app
  `reelstudio/audio.py`, OverlayView.fades) — blocked on M10
- M12b — subprocess execution: worker runs reel.py, manifest recorded
  post-job, delete graphs/ render.py assemble.py comfy_client.py stub.py,
  conftest stub reel.py — blocked on M12a
- M12c — preview mixer in Player (pure envelope/plan helpers + scheduled
  elements) + reel.py `bell` subcommand — blocked on M12a
- M12d — audio graph editor: peaks endpoint, PUT /api/audio/{i} (ruamel),
  waveform + anchor drag UI — blocked on M12a
- M12e — deploy + live verify (real `reel.py plan`, browser playback) —
  blocked on M12b..d

---

## M13 addendum — Asset inspector, selection-aware agent, Qwen reference pipeline (2026-10-18)

Requirements:

- FR-17: The stage's Images view is an asset browser: LEFT = a large
  interactive preview of the currently selected asset (images render full,
  audio renders a player), RIGHT = the thumbnail picker grid across the
  image+audio groups. Selecting in the grid updates the preview.
- FR-18: The agent knows what the operator is looking at: the chat request
  carries the current selection; a `currently_selected` tool returns the
  asset's slug, path, group, labels and used_by, so "regenerate this one"
  resolves without the operator naming files.
- FR-19: Free-form, typed asset labels at will: `char:<slug>`,
  `scene:<slug>` (foreign-key to the scene id), `cond:<x>` (human,
  were-tiger, …), any other free tag. `assets.yaml` stays the single owner
  of declared labels; the app writes it, never restates it.
- FR-20: `backgrounds/` folder in the workspace, enumerated as its own asset
  group with the same label machinery.
- FR-21: Qwen-Image-2.1 reference flow, executed by the workspace reel.py
  (single source of truth): (a) multi-view character sheets per character —
  front/profile/back/full-body from reference images, strict-roles prompt
  ("Picture 1 is the identity reference — preserve face/hair/outfit; Picture
  N the scene reference; do not blend identities"); (b) per-shot generation
  from 2–4 refs (character face/body + location plate) producing **10
  outputs per run with slight seed and prompt variations** for selection.
- FR-22: Reference images for Fox Kun and Tony exist, tagged `char:<slug>`
  (+ `cond:*` where applicable); scene images containing them carry both the
  char label and the scene FK label.

Milestones:

- M13a — Asset inspector: App lifts the full selection (slug/path/group),
  Stills.tsx → AssetBrowser (preview left, grid right, audio playback) —
  blocked on nothing
- M13b — `currently_selected` agent tool: chat POST carries the selection,
  ToolBox exposes it request-scoped — blocked on M13a
- M13c — Tagging: PUT /api/assets/labels (ruamel, comment-preserving),
  tag editor UI in the inspector, `backgrounds/` group in assets.py —
  blocked on M13a
- M13d — Workspace reel.py: `sheet` subcommand (multi-view character sheet,
  10 seed/prompt variants) + `shot` subcommand (per-shot 2–4 refs, strict
  roles, 10 variants) on the Qwen-Image-2.1 graph; generator registry wires
  `still`/`image_edit` — blocked on M13c
- M13e — Reference generation run: fox_kun + tony sheets and location plates
  into characters/ + backgrounds/, tagged; one per-shot demo run on the
  court scene — blocked on M13d
- M13f — Deploy + live verify (browser: inspector, tagging, agent tool) —
  blocked on M13b..e

Critical path M13a → M13c → M13d → M13e → M13f.

## M14 addendum — Multi-scene studio: wrapper YAML, File menu, cross-scene import (2026-10-18)

Requirements:

- FR-23: The workspace gains a wrapper layer ABOVE reel.yaml: a `studio.yaml`
  at the studio root — `{title, current, scenes: {slug: {title, dir}}}` — one
  entry per scene. Each scene is a self-contained directory (reel.yaml,
  assets.yaml, characters/, backgrounds/, sfx/, audio/, images/); `reel.py`
  stays ONE shared file at the studio root (the pipeline is never duplicated)
  and resolves its scene from the cwd it is invoked with (reel.yaml's home).
- FR-24: "Save reference to this scene": on a workspace with no studio.yaml,
  Save performs the migration — moves the project into `scenes/<slug>/`,
  writes the wrapper, and rebinds the app to the scene dir. On a migrated
  workspace it persists `current`/`title`.
- FR-25: The app resolves the studio by walking up from `config.workspace`
  (root-or-scene both accepted); scene switching rebinds config.workspace —
  `project()` already reloads from disk per call.
- FR-26: Import characters (pools) and locations (backgrounds) from another
  scene into the current one: copies the files and re-keys their declared
  labels, stripping `scene:*` foreign keys (they point at the source
  project's scenes); name collisions are refused.
- FR-27: Top-left File menu (chevron dropdown): Save, Open scene… (list,
  current checked), New scene… (slug + title + optional import of
  characters/locations from a chosen source scene).
- FR-28: The execution seam finds reel.py beside reel.yaml OR one level up
  (studio root) and keeps running it with cwd = the scene dir.

Milestones:

- M14a — `reelstudio/studio.py`: resolve/load/save/create/import + migration
  (save-as) — blocked on nothing
- M14b — Studio routes (GET /api/studio, POST open/save/scenes/import) +
  `get_studio`/`import_assets` agent tools — blocked on M14a
- M14c — reel.py cwd-aware scene resolution + seam walk-up (workspace repo) —
  blocked on nothing
- M14d — FE File menu (top-left) + new-scene dialog — blocked on M14b
- M14e — Migrate the live workspace, deploy + live verify — blocked on
  M14a..d

Critical path M14a → M14b → M14d → M14e (M14c parallel).

## M15 addendum — Fresh scenes, location pools, env-configured deployment (2026-10-18)

Requirements:

- FR-29: Scene creation is name-only: the dialog needs only a name; the
  slug derives server-side (snake_case of the name + a timestamp — no
  collisions, no slug field anywhere). A filled name always enables Create.
  (Revised 2026-10-18, later the same day: the operator wants NO slug input
  at all and a collision-proof derivation — snake_case + timestamp.)
- FR-30: `save_as()` never re-migrates: a workspace that resolves to a SAVED
  studio through an ancestor updates that studio's registry, whatever
  directory is configured. (Regression: 2026-10-18 12:18 — a Save click with
  the scene dir configured re-migrated, moving the scene into
  `scenes/court_aftermath/scenes/court_aftermath/`; the live workspace was
  repaired by hand.)
- FR-31: Import is OPTIONAL, never forced (revised 2026-10-18, overturning
  the same-day removal): scene creation has an opt-in "bring in characters &
  locations" toggle (source scene + pool picks); POST /studio/scenes carries
  the optional `import` spec; `import_assets` is restored (studio.py, route,
  agent tool) with location-pool semantics — a pool copies under its own
  name or merges into an existing pool via `as`, never clobbering files;
  the studio view exposes each scene's character/location pools.
- FR-31b: The Characters section's "+" opens the cross-scene import panel:
  every other scene's character pools, an editable target-pool name
  (defaulting to the source pool's name), and the upload path unchanged.
- FR-32: Backgrounds are location pools, modeled exactly like characters:
  `backgrounds/<location>/*.png`, derived `loc:<location>` labels, the Assets
  pane groups Backgrounds by location, uploads into Backgrounds ask for the
  location first, reel.py `bg` writes `backgrounds/<slug>/` and `plate_ref`
  finds plates there. The live scene's 20 flat plates migrate into
  `campus_sunset/` and `court_sunset/`.
- FR-33: Deployment is env-configured: every runtime knob is a REELSTUDIO_*
  env var (workspace, agent model, agent gateway URL, config path); a `.env`
  at the repo root is loaded by config.py (real env wins); `.env.example`
  owns the variable list; `docs/deployment.md` owns the deploy/migration
  story so any agent can ship this to another machine or gateway without
  re-deriving it. The local `.env` points at the garden gateway and the local
  ComfyUI.

Milestones:

- M15a — Live workspace repair + `save_as` ancestor fix + import removal
  (studio.py, app.py, agent/tools.py, agent skill docs) — blocked on nothing
- M15b — Location pools: assets.py indexer, reel.py bg/plate_ref, live
  backgrounds migration — blocked on nothing (parallel with M15a)
- M15c — Env config: config.py `.env` loader, `.env` + `.env.example`,
  docs/deployment.md, comfyui.service EnvironmentFile — blocked on nothing
  (parallel)
- M15d — FE: FileMenu title-first (no import), AssetsPane location pools,
  api.ts — blocked on M15a, M15b
- M15e — Tests (BE + FE), frontend build → web/dist, deploy (comfyui
  restart) + live verify — blocked on M15a..d

Critical path M15a/M15b/M15c → M15d → M15e.
