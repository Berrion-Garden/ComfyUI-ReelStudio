---
name: agent-workflow
description: The Reel Studio agent tool protocol — get_project staleness reading, update_yaml mechanics, render_scenes vs stale, music, assemble, and what to report to the user. Load before using any tool.
---
# Agent workflow

## Tool protocol

- `update_yaml` replaces the WHOLE file and is validate-gated: one atomic
  edit per call. ALWAYS `get_yaml` first, edit that text, submit the complete
  file. On a validation error, fix the SAME text and retry — never re-read
  and start over.
- `get_project` is the read model: per-scene `stale`, `rendered`,
  `start_s`, `duration_s`, anchor kinds. Read it before and after every edit.
- `render_scenes` takes explicit `scene_ids` (rendered upstream-first) or
  `{stale: true}` for every stale scene. NEVER render the whole chain when
  two scenes changed.
- `render_music` regenerates one named segment. `assemble` is the final
  production — only run it when the user asks for the final mix.
- `get_status` reports queued/running/done/error jobs. Renders are minutes
  per scene on the GPU node; report what was queued, do not poll silently.

## The loop for "change X"

1. `get_project` → find the affected scene(s) and who anchors on them
   (junction-doctrine decides the re-render set).
2. `get_yaml` → `update_yaml` with the edit.
3. State what changed in one or two sentences.
4. `render_scenes` with exactly the affected set (offer first unless the user
   already asked for regeneration).
5. Report: edited scenes, re-rendered scenes (and WHY a downstream scene was
   included), what stayed untouched.

## Rules

1. NEVER save YAML you have not validated mentally against reel-yaml-schema;
   a broken chain blocks the whole app until fixed.
2. NEVER invent scene ids — ids come from `get_project`.
3. When the user asks "make it shorter", change `frames:` (generation length)
   and adjust the description; NEVER cut frames after the fact.
4. When an edit only touches `music:` or `sound_effects:`, say so — sound
   changes still re-render the scene (H3 bakes the soundscape) but never
   cascade to still-anchored neighbours.
