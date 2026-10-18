---
name: app-troubleshooting
description: Reel Studio failure modes — validation errors, missing renders, junction pops, off-grid frames, stale that will not clear, assemble failures. Load when diagnosing.
---
# Troubleshooting

## Validation errors (update_yaml rejected)

- "chain break at X" — `next:` disagrees with list order. Fix `next:` to point
  at the following scene's id; the last scene gets `next: null`.
- "first scene cannot anchor on prev_last" — the first scene needs a still or
  null first anchor.
- "unknown still ref" — add the entry to `stills:` (value is the basename
  WITHOUT the `_.png` suffix the resolver appends).
- Off-grid warning (17n+5) — allowed, renders anyway. Do not "fix" a working
  scene length because of the warning.

## Renders

- "upstream X has no render — render it first" — a `prev_last` scene was
  queued before its upstream existed. Render upstream-first or use
  `generate` with `stale: true`.
- Comfy reports success but no render landed — `meta.reel_dir` must sit under
  ComfyUI's output dir; `SaveVideo` writes there via `filename_prefix`.
- Renders are produced by the workspace's `reel.py` (the only pipeline
  implementation) run as a subprocess by the studio — the studio itself never
  talks to ComfyUI or ffmpeg. If a render job fails, the job error carries
  reel.py's log tail; fix the pipeline there, not in the app.
- A scene rendered but still shows stale — its junction partner re-rendered
  (junction identity), or the manifest predates the app. For pre-app renders
  run the adopt action once (`POST /api/manifest/adopt`, or the agent's
  `adopt_renders` tool) — it records existing deliverables as current
  against the present config. After adopting, only genuine config/junction
  drift shows stale.

## Assemble

- "scene X has no render — cannot assemble" — every scene needs a deliverable
  before the mix; render the XXX slices first.
- "no audio for music segment" — the segment was never generated; run
  `generate` with kind `music` for it (or keep `flags.skip_music: true` for a
  sfx-only mix).

## App bugs that only show in production

- The PromptServer mount (server.py) must carry everything app-level with the
  routes: state, the job-worker lifecycle hooks, and the middlewares. A 4xx
  that appears as a 500 only through ComfyUI — but passes in tests — means a
  piece of the standalone app didn't travel with the mount.

## Quality (renders fine, looks wrong)

- Junction pop at a cut → junction-doctrine rule 5.
- Object re-manifests mid-scene → junction-doctrine rule 3/4; harden with an
  exit-frame anchor, not a longer negative list.
- Text artifacts in frame → H3 never renders text; remove any text-like
  description words, move labels to `post.freeze.names`.
- Camera drifts when it should hold → restate "The camera holds a
  near-static shot" and pin the background as FIXED in the description.
