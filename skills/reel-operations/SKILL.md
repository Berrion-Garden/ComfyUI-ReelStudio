---
name: reel-operations
description: >
  Operations manual for the studio chat agent on the Amun reel
  (llm_engine_management/anime_reel/reel.py): segment re-renders, the
  anchor-still campaign seam (drafts/finals waves, serving profile, wedge
  recovery), judge flow with atomic assets.yaml tagging, storyboard beat
  wiring, keyframe re-rolls, timing re-cuts, music + assemble verification.
  Use when rendering, judging, tagging picks, wiring beats, re-cutting
  frames, or assembling the final mp4.
---

# Amun reel operations

```bash
SCENE=$HOME/Side_Projects/llm_engine_management/anime_reel/scenes/amuns-reveal
REEL=$HOME/Side_Projects/llm_engine_management/anime_reel/reel.py
PY=/home/kyle/comfy-py311-env/bin/python
cd "$SCENE" && export REEL_SCENE=$PWD     # every command runs from the scene dir
```

Cross-refs: `reel-review` (`llm_engine_management/.opencode/skills/`) owns the review ladder + pass bars; `comfyui-serving` owns serving mechanics; `reel-yaml-schema` (this repo's skills/) owns the yaml contract.

## Hard rules

1. Budgets are the only sanctioned waits. A graph past budget = THRASH (wrong profile, weight streaming, wedge) — tune, never wait. Measured: draft graph ~11 s, 25-step ~35 s, one H3 scene 3-6 min.
2. NEVER run the studio rollout while a wave is live — `campaign()` owns restarts/re-warms; a mid-wave rollout kills a running render.
3. NEVER write `assets.yaml` non-atomically (temp file + `os.replace`) — the running app parses it on every poll; a half-written file storms it.
4. NEVER `pkill -f <unbracketed>` — it matches your own shell; use `pgrep -f "[b]racketed"` or exact PIDs.
5. Submits are refused above 20 queued graphs (a backlog starves every budget). Drain: `curl -X POST http://localhost:8188/queue -d '{"clear": true}'`.

## 1. Re-render video segments

```bash
$PY "$REEL" plan                        # chain OK + start times + music map (read-only)
$PY "$REEL" render s07_bridge s08_gate  # subset, in chain order
$PY "$REEL" render                      # whole chain
$PY "$REEL" post s20_title              # freeze post only, no re-render
```

- Touches: the ComfyUI queue (H3, 900 s budget/scene) and `meta.reel_dir` (`<id>_NN_*.mp4`). `deliverable()` takes the NEWEST render — re-running a scene supersedes the old clip; freeze outputs (`_9_freeze_`) sort last and win.
- Resume after a crash: just re-run the command — ids sort. `first: prev_last` reads the previous scene's current deliverable, so re-render downstream scenes after an upstream change. `render` re-runs the freeze post + sfx split itself; `assemble` (§7) after any deliverable changed.

## 2. Anchor-still campaign (the render-wave seam)

`campaign()` owns the serving profile switch, restart, pinned-weight warm, batch halving on OOM, and wedge recovery — never manage the server by hand around a wave. The runner imports the pipeline once per process: mid-flight reel.py edits land on the NEXT wave, never mid-wave.

```bash
$PY "$REEL" preflight                   # gate: profile=image + empty queue + warm
$PY "$REEL" campaign 10                 # DRAFTS: all leaves, variants=10, steps=8, batch=2
# FINALS (CLI cannot set steps=25 — call the function):
$PY -c "import os, runpy; g = runpy.run_path('$REEL'); g['campaign'](leaves=['amun_ignite'], variants=2, steps=25, batch=2, final=True)"
```

- Drafts select composition (turbo LoRA, 8 steps, 512x288); finals re-render the picks at 1024x576 (no LoRA, 25 steps) carrying the `final` label — `resolve_still` prefers the final copy when both exist.
- A leaf failing twice (OOM halves the batch first, then restart + re-warm + retry) is reported and SKIPPED — read `CAMPAIGN_DONE failed=[...]`, never assume all-done.

## 3. Judge flow (drafts → pick → finals → tag)

1. Contact sheet per leaf (PIL): REF cell + `#1`-`#10` — recipe in `reel-review` §3.
2. Subagent judges: ≤3 sheets each (4-image cap). Consolidate to a verdict per leaf: `PICK #n` or `NONE` + failing gate (`wardrobe | identity | beat`). NONE is never a same-text re-roll — edit the pose language (§5); same text + the same seed ladder reproduces the same images.
3. Tag the pick in `assets.yaml` — ATOMIC, the app polls this file:

```bash
$PY - <<'EOF'
import os, tempfile, yaml
leaf, n = 'amun_ignite', '07'                    # still_dir/amun_igniteNN_00001_.png
doc = yaml.safe_load(open('assets.yaml')) or {}
labels = doc.setdefault('labels', {})
key = f'{leaf}{n}_00001_.png'                    # bare filename: stills live in still_dir
labels[key] = sorted(set(labels.get(key, []) + [f'still:{leaf}']))
fd, tmp = tempfile.mkstemp(dir='.')
with os.fdopen(fd, 'w') as fh:
    yaml.safe_dump(doc, fh, sort_keys=False, allow_unicode=True)
os.replace(tmp, 'assets.yaml')                   # atomic: temp + rename
EOF
```

4. Finals for the picked leaves (§2 `final=True`), then move the `still:<leaf>` tag onto the final-labeled copy (same block) — the resolver prefers the final copy, but one pick of record beats two. Verify the anchors resolve: `$PY "$REEL" collapse`.

## 4. Update narrative (beat text)

- `storyboard.yaml` (beside the scene tree) is the SSOT for beat language: acts → checkpoints → shots; the shot id is the first word of `title`, the text is the prompt. Edit THERE, never in reel.yaml — a wired scene's `video.description` is composed at import from `beat:` + shot text.
- Wire a new/renamed shot: set the scene's `beat: '<shot id>'` in reel.yaml.

```bash
$PY "$REEL" plan | head -3              # compose runs at import — "chain OK — 23 scenes, 86.250 s"; an unknown beat exits loudly
curl -sf http://127.0.0.1:8188/reelstudio/api/project >/dev/null && echo API-OK
```

## 5. Update a keyframe (anchor still)

- Edit the leaf's entry in reel.yaml `shots:` — pose, props, `layer:`, `compose:`, `negatives:` only. Beat language lives in storyboard.yaml (§4); wardrobe canon lives in `characters.<slug>.layers`.
- Re-roll, judge, tag, final — the §3 loop for one leaf:

```bash
$PY "$REEL" shot amun_ignite            # 10 draft variants, steps=8, batch=1
$PY "$REEL" campaign 10                 # or the whole wave when many leaves changed
```

## 6. Re-cut timing

- Per-scene `frames:` (all 90 here = 17×5+5) — stay on the H3 grid 17n+5; off-grid works but the studio validator warns. Duration = frames/24.
- Music act anchors: the `music: {name, caption, gain}` dict sits on the act-OPENING scene and runs to the next anchor. RULING (operator, 2026-10-22): generated audio is NEVER mixed — the wired song track is the only bed, and `sfx_volume: 0` keeps H3 scene audio out. The Amun reel carries NO `music:` anchors; do not re-add them without instruction.
- Title freeze post (s20): `at_s` (motion), `flash_s` (white hit), `grade` (saturation/contrast/brightness/vignette), `names` (drawtext credits — `x` is NUMERIC pixels; only the literal `right` slides from the right edge). Edit `post:` → `$PY "$REEL" post s20_title`, verify with `plan` + validator API-OK (§4).

## 7. Music + assemble

```bash
$PY "$REEL" music                       # no-op unless `music:` anchors exist — the Amun reel has NONE (see the ruling in §6)
$PY "$REEL" assemble                    # bed + bells + sfx + concat + mix -> final mp4
```

- The mix's ONLY bed is the wired song track (`audio:` in reel.yaml). Generated music and H3 scene audio are both mixed at zero gain (no `music:` anchors + `sfx_volume: 0`). Before claiming the mix is missing a layer, trace the LAST assemble's `overlay:` lines — the mix log is ground truth, not the storyboard's wish list.

- `music`/`assemble` both skip music only under `flags.skip_music: true` in reel.yaml (NOT set for the Amun reel — they include music by default); `--with-music` forces past that flag.
- Verify the cut (final = `meta.final`):

```bash
OUT=/home/kyle/comfy/ComfyUI/output/amuns-reveal_reel.mp4
ffprobe -v error -show_entries format=duration -of csv=p=0 "$OUT"      # 86.25 = 23 x 3.75 s
ffprobe -v error -select_streams v:0 -show_entries stream=width,height -of csv=p=0 "$OUT"  # 1024,576
$PY "$REEL" plan | grep s20_title      # start time for the title-frame extraction
```

Extract the s20 midpoint frame (start + 1.875 s): the AMUNREKH / The Undead Wizard title card must show; the final frames fade to black. Full pass bar: `reel-review` §6.

## 8. Serving profile

- Image waves (campaign) vs video waves (render) need different boot profiles. `campaign()` switches to `image` and restarts automatically; `preflight` refuses otherwise. Manual switch:

```bash
echo image > ~/.config/comfyui-serving/profile    # or: video
systemctl --user restart comfyui.service
until curl -sf http://localhost:8188/system_stats >/dev/null; do sleep 2; done
```

- H3 can never pin weights (42.4 GB > device limit) — video takes dynamic mode; image without the pinned flags weight-streams at 24-36 s/graph and blows every budget. Mechanics: `comfyui-serving` skill.

## 8b. Re-attaching external renders to the studio UI

After restructuring scene ids, or after any render done outside the studio's own generate flow, the Player shows "No renders yet" and the timeline shows X on anchor slots. The app tracks renders in `<reel_dir>/.reelstudio_manifest.json` (keyed by CURRENT scene ids — a manifest entry under an old id does not match), and resolves `still:<name>` anchors to a literal `<name>_.png` in `still_dir` (it cannot disambiguate the draft/final label sharing in assets.yaml — ambiguous labels resolve to nothing). Fix both:

```bash
# 1. anchor thumbs: materialize the judged finals under the app's convention
#    (run from the scene dir; uses reel.py's own resolver, which prefers the `final` copy)
$PY - <<'EOF'
import sys, os, shutil; sys.path.insert(0, '<repo>/anime_reel')
import reel
names = {s['video'][side].removeprefix('still:') for s in reel.CFG['scenes'] for side in ('first','last')}
for n in names:
    src = reel.resolve_path(f'still:{n}', None)
    dst = os.path.join(reel.M['still_dir'], f'{n}_.png')
    if src and not os.path.exists(dst): shutil.copy2(src, dst)
EOF

# 2. player: adopt the on-disk mp4s for the current ids
curl -s -X POST http://127.0.0.1:8188/reelstudio/api/manifest/adopt -d '{}' -H 'Content-Type: application/json'

# 3. verify
curl -s http://localhost:8188/reelstudio/api/project -o /dev/null -w '%{http_code}\n'   # 200
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8188/reelstudio/api/scene/<sid>/artifact/video
```

Adoption caches the current config collapse as the staleness baseline — adopt only when the renders really match the current reel.yaml.

## 9. Guardrails

- A wedge (HTTP dead, GPU 0%): restart, wait `/system_stats` 200, re-warm (`$PY "$REEL" warmup`, 300 s budget), retry — inside a campaign this is automatic; never hand-recover mid-wave.
- The Hard rules above all have burned hours behind them; §1-§8 name the re-run after every change: re-render → collapse/plan → assemble → the §7 verification.
