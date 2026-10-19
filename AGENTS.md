# ComfyUI-ReelStudio — agent instructions

The studio's own agent loads its skills from `skills/`; this file is for
coding agents working in the repo. Fleet-global rules:
`~/.config/opencode/AGENTS.md`.

## Rollout — the only supported way to land changes

`./rollout.sh` — builds the UI (`frontend/` → `web/dist/`), restarts the
ComfyUI service only when backend python changed, then verifies the deployed
endpoint against `REELSTUDIO_PUBLIC_URL` from the repo-root `.env`.

- The deployed app is served from the **running ComfyUI process**: python
  edits are not live until the service restarts, and the browser serves the
  page from `web/dist` on disk. Build + commit alone is not a rollout — the
  operator's UI keeps running old handlers and "nothing happens".
- A rollout is complete when `./rollout.sh` prints its verification lines
  (local bundle, public bundle, public API). Never claim backend changes
  landed without that proof against the public endpoint.
- Wiring is env-driven: the repo-root `.env` per machine, variable owner
  `.env.example`, deployment story `docs/deployment.md`. The manual recipe
  (`npm run build && cp -r dist/* ../web/dist/`) ships the UI only and leaves
  the backend stale — it is an install step, not a rollout.

## Master plan

`docs/plans/2026-10-16-reel-studio/plan.md` is GOVERNING for pipeline and
architecture work; off-plan work is stopped and reported.

## Tests

- frontend: `cd frontend && npm test` (vitest) and `npx tsc -b`
- backend: `.venv/bin/python -m pytest tests/`
