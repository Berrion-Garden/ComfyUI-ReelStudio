# Reel Studio — deployment & configuration

> **Keywords:** reelstudio, REELSTUDIO_WORKSPACE, REELSTUDIO_AGENT_MODEL,
> REELSTUDIO_AGENT_BASE_URL, REELSTUDIO_CONFIG, REELSTUDIO_ENV, .env,
> rollout.sh, REELSTUDIO_COMFYUI_SERVICE, REELSTUDIO_LOCAL_URL,
> REELSTUDIO_PUBLIC_URL, comfyui.service, custom_nodes, web/dist,
> EnvironmentFile, 8188, deployment.
> **Portability:** HIGH (mechanism); the Wiring section is CURRENT-STATE for
> this node (2026-10-18).

**What:** how Reel Studio is deployed, how it is configured (env-first), and
how to move it to another machine, workspace, or LLM gateway — the no-research
path for any agent or operator.

**Why:** every runtime knob (which workspace, which agent model, which
gateway) is environment configuration, never code. A new machine or a
different remote LLM is a `.env` edit + service restart, and two agents never
need to re-derive the wiring.

**How:**

1. **Config precedence** (owned by `reelstudio/config.py`): real environment
   variables → `.env` → `~/.config/reelstudio/config.json` → defaults. The
   variable list lives in `.env.example` (the single owner); a repo-root
   `.env` is the per-machine file and is gitignored.
2. **Variables:**
   - `REELSTUDIO_WORKSPACE` — the studio root or any scene dir (holds
     `reel.yaml` + `reel.py`).
   - `REELSTUDIO_AGENT_MODEL` — the chat agent's model alias on the gateway.
   - `REELSTUDIO_AGENT_BASE_URL` — any OpenAI-compatible gateway
     (`/v1`). Pointing at a different remote LLM is this one variable.
   - `REELSTUDIO_CONFIG`, `REELSTUDIO_ENV` — optional overrides for the
     config.json and .env paths.
3. **Install (new machine):** make the repo importable as a ComfyUI custom
   node — symlink or clone it into `ComfyUI/custom_nodes/ComfyUI-ReelStudio`.
   Build the UI: `cd frontend && npm ci && npm run build`, then
   `cp -r frontend/dist/* web/dist/` (the server serves `web/dist`).
4. **Wire the env:** `cp .env.example .env`, edit for the machine, and add
   `EnvironmentFile=-<repo>/.env` to the ComfyUI user unit, then
   `systemctl --user daemon-reload && systemctl --user restart comfyui`.
5. **Verify:** `curl localhost:8188/reelstudio/api/project` and
   `/reelstudio/api/studio` return 200; the UI is at
   `http://<host>:8188/reelstudio`.
6. **Rollout (day-2, this machine):** `./rollout.sh` — builds the UI, ships
   `web/dist`, restarts `comfyui.service` only when backend python changed
   (python lives in the running process), and verifies the local and public
   endpoints (public from `REELSTUDIO_PUBLIC_URL` in `.env`). Referenced from
   the repo `AGENTS.md`; the manual build+copy line above is the install
   step, not a rollout.
7. **Migrating the workspace:** a workspace is self-contained (studio.yaml,
   scenes/, reel.py at the root) — copy the directory, point
   `REELSTUDIO_WORKSPACE` at it, restart. Nothing else moves.

**Numbers (this node, 2026-10-18):** repo at
`~/Side_Projects/ComfyUI-ReelStudio`, symlinked into
`~/comfy/ComfyUI/custom_nodes/ComfyUI-ReelStudio`; ComfyUI as the
`comfyui.service` user unit on `127.0.0.1:8188` (proxy 54000, public
`comfy.berrion.garden`); workspace
`~/Side_Projects/llm_engine_management/anime_reel`; gateway
`https://llms.berrion.garden/v1`, model `writer` — all pinned in the repo
`.env`.
