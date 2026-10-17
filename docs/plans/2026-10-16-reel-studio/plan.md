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
