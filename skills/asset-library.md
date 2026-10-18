---
name: asset-library
description: The derived asset library — scenes/characters/custom/themes/audio groups, labels, used_by, assets.yaml. Load before picking anchor images or naming any asset.
---
# Asset library

Everything in the library is **derived, never hand-indexed** — `get_assets`
computes it per request:

- **Scenes** — the images reel.yaml's `stills:` map actually anchors on. Each
  carries `still:<name>` plus `used_by:<scene>` for every scene that
  references it, so a still's downstream is always visible.
- **Characters** — pose pools under `characters/<slug>/`, labelled
  `char:<slug>` and `pose:<file>`. Update a pool and every label that names
  it updates with it.
- **Custom** — anything the operator drops into `images/`.
- **LORA / Theme** — `themes/<slug>.yaml` descriptors (`slug`, `lora`,
  `trigger`, `labels`).
- **Audio** — rendered music segments plus anything under `audio/`.

`assets.yaml` in the workspace attaches extra labels to any
workspace-relative path:

```yaml
labels:
  characters/fox_boy/run_.png: [hero, main-walk]
```

Because labels name pools and scenes rather than individual files, refreshing
a character pool and re-deriving is the same operation for you as for a
human: read the labels, regenerate what points at them.

## Rules

1. Anchor scenes with `still:<name>` refs into named library stills — never
   literal paths into `still_dir` when a named still exists.
2. A still that `get_project` shows `present: false` is a broken anchor:
   the file is missing from the external Qwen-Image pipeline's output.
3. `still` / `image_edit` generation is NOT wired — new or changed stills
   come from the operator's external Qwen-Image pipeline; ask, then reference
   the result by name.
