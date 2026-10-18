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
