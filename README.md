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
├───────────────────────────────┬────────────────────────────────────┤
│  ▶ full-video preview         │  Assets                            │
│    (or the selected image)    │  ▸ Characters  ▸ Scenes  ▸ Custom  │
│                               │  ▸ LORA/Theme  ▸ Audio             │
├───────────────────────────────┴────────────────────────────────────┤
│ 0s      5s      10s      15s   ← scrub anywhere on the timeline    │
│  ▏ first ▏ last  ▕ ▏ first ▏ last  ▕ ▏ first ▏ last  ▕   anchors   │
│  ▏ ── video ──   ▕ ▏ ── video ──   ▕ ▏    XXX     ▕   video lane  │
│  ▏ ══ opening ═══════▕ ▏    XXX     ▕                 music lanes │
│  ▏ ▏ ══ battle ═════════════════════▕                               │
├────────────────────────────────────────────────────────────────────┤
│  chat: "make scene 2 shorter" → YAML edit → re-render s2 (+s3)     │
└────────────────────────────────────────────────────────────────────┘
```

- **Timeline** — a proportional grid of lanes: anchor thumbnails
  (`prev_last` shown as `⟵ prev`), the video deliverable, and one lane per
  music segment showing exactly which scenes it spans. `XXX` marks what
  doesn't exist yet; a dashed outline marks what is stale. Click or drag
  anywhere on the timeline to scrub the preview to that point.
- **Assets** — the library pane groups everything by derivation (see
  "Asset library" below). Selecting an image shows it in the player via the
  🖼 toggle; arrow keys walk the library.
- **Render changed** — staleness is hash-based: a scene is stale when its
  generation-relevant config changed **or** the upstream deliverable it
  anchored on (`prev_last`) was re-rendered — junctions stay frame-exact,
  and nothing else re-renders.
- **Preview chain** — plays rendered scenes back to back through two
  trading `<video>` elements. Nothing is concatenated.
- **Final production** — the only step that stitches: music bed, synth bell,
  concat, fade, mix → `meta.final`.
- **Agent** — chats over the Berrion garden gateway (OpenAI-compatible);
  tools: the shared read model (`get_project`), the derived asset library
  (`get_assets`), validate-gated YAML read/edit, one `generate` seam over
  every generator (scene / music / assemble wired; still / image_edit
  declared but unwired), and job status.

## The YAML

Inherited from the anime_reel pipeline — scenes chain by `next:` slugs, each
with `video` (mode i2v/fl2v/t2v, `first`/`last` anchors: `prev_last`,
`still:<name>`, or a path; description; negative), `sound_effects`
(soundscape baked into the clip by H3; `bell` for the synth bell), `music`
(segment anchored at that scene, runs to the next anchor; `gain`), optional
`post.freeze` (motion → flash → graded freeze with name credits), and
per-scene `frames` (the scene-length lever — length is **generated**, never
cut; off the 17n+5 H3 grid is allowed but warned).

Shared look machinery keeps scene notes focused: `styles:` names look blocks
(`pro`/`con`) with `style:` picking the active one — its `pro` is prepended
to every video prompt and its `con` merged into every negative, so one edit
re-styles the whole reel. `locations:` are slugged location blocks a scene
references with `location:`; only those scenes get the injection. Vocabulary
and pro/con doctrine: `skills/film-grammar.md`.

Staleness is diff-based: the workspace's `reel.py collapse` merges the yaml
into each scene's final generation input; the studio caches it in the
manifest and re-renders exactly the scenes whose input changed.

## Asset library

Everything in the library is **derived, never hand-indexed** — the API response
is the index, computed per request:

- **Scenes** — the images reel.yaml's `stills:` map actually anchors on. Each
  gets `still:<name>` plus `used_by:<scene>` for every scene that references
  it, so a still's downstream is always visible.
- **Characters** — pose pools under `characters/<slug>/`. Each image gets
  `char:<slug>` and `pose:<file>`; update a pool and every label that names it
  updates with it.
- **Custom** — anything under `images/`.
- **LORA / Theme** — `themes/<slug>.yaml` descriptors (`slug`, `lora`,
  `trigger`, `labels`).
- **Audio** — rendered music segments (newest file wins, even if it predates
  the manifest) plus anything under `audio/`.

Cross-grouping is programmatic: `assets.yaml` in the workspace attaches extra
labels to any workspace-relative path —

```yaml
labels:
  characters/fox_boy/run_.png: [hero, main-walk]
```

Because labels name pools and scenes rather than individual files, refreshing a
character pool and re-deriving is the same operation for the agent as for a
human: read the labels, regenerate what points at them.

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
{ "workspace": "...",
  "agent_model": "orchestrator",
  "agent_base_url": "https://llms.berrion.garden/v1" }
```

The web UI is prebuilt into `web/dist/`. To rebuild it:
`cd frontend && npm run build && cp -r dist/* ../web/dist/`.

### Standalone (no ComfyUI)

The app runs without ComfyUI around it — useful for development and for
scripting against the HTTP API:

```bash
.venv/bin/reelstudio serve --port 8287     # or: python -m reelstudio.server
```

## Testing

Two-tier, all runnable without a GPU:

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest                # backend, incl. agent loop tests
cd frontend && npm ci && npm test         # frontend
```

Tests execute the pipeline through a STUB `reel.py` shipped in the fixture
workspace — the same CLI contract as the real pipeline (render, music,
assemble, bell, collapse), writing real tiny deliverables. The live GPU node
at 8188 is never touched by tests.

## Architecture

```
reelstudio/
  project.py      reel.yaml model + validation (chain, anchors, looks, post)
  timeline.py     duration math; staleness = collapse diff, hash fallback
  collapse.py     the collapse: reel.py's merged generation input, cached
  manifest.py     .reelstudio_manifest.json — what was rendered from what
  reel.py         the subprocess seam to the workspace's pipeline script
  generate.py     the generation registry — one entry per generator kind
  readmodel.py    one project/asset read model, shared by API and agent
  agent/          gateway client, tool box, SSE agentic loop, skill loader
  app.py          aiohttp routes + render queue (single GPU worker)
  server.py       the one adapter: mounts app.py onto ComfyUI's PromptServer
                  (`reelstudio serve` runs the same app standalone)
```

Design rule: the workspace's `reel.py` is the only pipeline implementation
(the single source of truth for touching ComfyUI/ffmpeg); everything in this
repo is testable without a server.

## Skills (agent injection)

The in-app agent's system prompt is assembled from the markdown skills in
[`skills/`](skills/) — one concern per file, open Agent Skills format.
Skills flagged `always: true` in their frontmatter are injected whole every
turn (the editing spine: `agent-workflow`, `reel-yaml-schema`,
`h3-prompting`); the rest are advertised as a one-line index and the agent
pulls them whole with its `get_skill` tool when a task matches — deep
vocabulary is a roundtrip, not always-on context:

- `reel-yaml-schema` *(always)* — the full YAML contract
- `h3-prompting` *(always)* — writing H3 descriptions/negatives/soundscapes
- `agent-workflow` *(always)* — the tool protocol (validate-gated
  `update_yaml`, the `generate` kinds, render only what changed)
- `film-grammar` — condensed shot/lighting/color vocabulary, every term with
  pro (prompt) and con (negative) words
- `junction-doctrine` — chaining, `prev_last` frame-exactness, the
  "never show the landing" lesson
- `asset-library` — the derived library: groups, labels, `used_by`
- `app-troubleshooting` — failure modes and fixes

Edit a skill and the agent knows it on the next chat turn; nothing to rebuild.
Override the directory with `REELSTUDIO_SKILLS_DIR`.

## Stub pipeline (no GPU needed)

There is no stub mode in the app — the app only runs the workspace's
`reel.py`. To exercise the whole flow without a GPU (chain rendering,
`prev_last` junctions, freeze post, assembly, the agent, collapse staleness),
point `REELSTUDIO_WORKSPACE` at a workspace whose `reel.py` is a stub
implementing the same CLI contract: `render <id...>`, `music`, `assemble`,
`bell [out]`, `collapse` — see the reference stub in `tests/conftest.py`.
Live workspaces use the real pipeline unchanged.
