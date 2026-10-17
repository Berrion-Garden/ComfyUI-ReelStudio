# ComfyUI-ReelStudio

**Reel Studio** — a ComfyUI app for YAML-driven scene-chain video production
(MiniMax H3 + Music 3). One `reel.yaml` is the single source of truth; the app
gives you a timeline to edit it visually, renders only what changed, previews
the chain as though it were stitched, and ships a chat agent that edits the
YAML and re-renders for you.

Born from the Court Aftermath pipeline (`anime_reel/reel.py` + `reel.yaml`).

## What it does

```
┌────────────────────────────────────────────────────────────────────┐
│ Reel Studio                                            ⟳ Render    │
├────────────────────────────────────────────────────────────────────┤
│  ▏scene 1        ▕ ▏scene 2        ▕ ▏scene 3        ▕             │
│  ▏ first ▏ last  ▕ ▏ first ▏ last  ▕ ▏ first ▏ last  ▕   anchors   │
│  ▏ ── video ──   ▕ ▏ ── video ──   ▕ ▏    XXX     ▕   video row   │
│  ▏ ── audio ──   ▕ ▏    XXX     ▕ ▏ ── audio ──   ▕   audio rows  │
│  ▏ ── music ──   ▕ ▏             ▕ ▏             ▕               │
├────────────────────────────────────────────────────────────────────┤
│  ▶ Preview chain  (seamless, nothing stitched)                     │
├────────────────────────────────────────────────────────────────────┤
│  chat: "make scene 2 shorter" → YAML edit → re-render s2 (+s3)     │
└────────────────────────────────────────────────────────────────────┘
```

- **Timeline** — one vertical slice per scene along a time axis; anchor
  thumbnails on top (`prev_last` shown as `⟵ prev`), the video deliverable
  below it, the baked clip audio and any anchored music segment under that.
  `XXX` marks what doesn't exist yet; a dashed outline marks what is stale.
- **Render changed** — staleness is hash-based: a scene is stale when its
  generation-relevant config changed **or** the upstream deliverable it
  anchored on (`prev_last`) was re-rendered — junctions stay frame-exact,
  and nothing else re-renders.
- **Preview chain** — plays rendered scenes back to back through two
  trading `<video>` elements. Nothing is concatenated.
- **Final production** — the only step that stitches: music bed, synth bell,
  concat, fade, mix → `meta.final`.
- **Agent** — chats over the Berrion garden gateway (OpenAI-compatible);
  tools: read/edit YAML (validate-gated), render scenes/stale, music,
  assemble, status.

## The YAML

Inherited from the anime_reel pipeline — scenes chain by `next:` slugs, each
with `video` (mode i2v/fl2v/t2v, `first`/`last` anchors: `prev_last`,
`still:<name>`, or a path; description; negative), `sound_effects`
(soundscape baked into the clip by H3; `bell` for the synth bell), `music`
(segment anchored at that scene, runs to the next anchor; `gain`), optional
`post.freeze` (motion → flash → graded freeze with name credits), and
per-scene `frames` (the scene-length lever — length is **generated**, never
cut; off the 17n+5 H3 grid is allowed but warned).

## Install

```bash
git clone https://github.com/Berrion-Garden/ComfyUI-ReelStudio.git \
    ~/comfy/ComfyUI/custom_nodes/ComfyUI-ReelStudio
```

Restart ComfyUI, then open `http://<comfy>:8188/reelstudio`.

Point it at a reel workspace (a directory with a `reel.yaml`):

```bash
export REELSTUDIO_WORKSPACE=/home/kyle/Side_Projects/llm_engine_management/anime_reel
```

or `~/.config/reelstudio/config.json`:

```json
{ "workspace": "...", "comfy_url": "http://localhost:8188",
  "agent_model": "orchestrator",
  "agent_base_url": "https://llms.berrion.garden/v1" }
```

The web UI is prebuilt into `web/dist/`. To rebuild it:
`cd frontend && npm ci && npm run build && cp -r dist ../web/`.

## Testing

Two-tier, all runnable without a GPU:

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest                # 29 tests
cd frontend && npm ci && npm test         # 19 tests
```

Integration tests run against a **fake ComfyUI on the isolated endpoint
`127.0.0.1:8288`** with real ffmpeg tiny clips — the live GPU node at 8188 is
never touched by tests. The fake server executes graphs synchronously and
writes deliverables exactly where `SaveVideo` would.

## Architecture

```
reelstudio/
  project.py      reel.yaml model + validation (chain, anchors, music, post)
  timeline.py     duration math, config hashes, staleness (config + junction identity)
  manifest.py     .reelstudio_manifest.json — what was rendered from what
  graphs/         pure graph builders (h3_video, music3) — golden-tested
  comfy_client.py the only HTTP seam to Comfy (/prompt, /history, inputs)
  render.py       scene render + freeze post + music segments
  assemble.py     music bed + bell + concat + mix (the ONLY concat step)
  agent/          gateway client, tool box, SSE agentic loop
  app.py          aiohttp routes + render queue (single GPU worker)
  server.py       the one adapter: mounts app.py onto ComfyUI's PromptServer
```

Design rule: everything except `comfy_client.py` and `server.py` is testable
without a server. The isolated endpoint (`8288`) exists so worktree and CI
testing can never interfere with the live node.
