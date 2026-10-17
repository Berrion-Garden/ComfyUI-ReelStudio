---
name: junction-doctrine
description: Scene chaining and prev_last junction frame-exactness — when a downstream scene must re-render, anchoring state in imagery, the "never show the landing" lesson. Load before any edit that touches scene order, anchors, or endings.
---
# Junction doctrine

## The mechanism

`first: prev_last` starts a scene on the previous scene's ACTUAL last frame.
That is the whole continuity mechanism — there is no cross-scene prompt
context. Two consequences:

1. **A re-render upstream invalidates the downstream anchor**, even with an
   unchanged config (a new seed produces a new last frame). The app's
   staleness tracks this via junction identity: the downstream scene goes
   stale and MUST be re-rendered in the same pass to keep the cut frame-exact.
2. A still-anchored scene (`first: still:...`) does NOT cascade — its anchor
   is a file, not the upstream render. Only re-render it if you change IT.

## Rules

1. NEVER let an upstream ending change ship without re-rendering the
   `prev_last` scene behind it. Render upstream-first (the app orders the
   queue this way) so the chain resolves in one pass.
2. NEVER change `frames:` on a scene without checking who anchors on its new
   ending.
3. Anchor state in IMAGERY, not in negatives: a scene that must start
   "hands empty" should start on a frame where the hands are provably empty —
   a short exit scene ending on empty hands, then `prev_last`. A negative
   prompt is a backup, never the anchor.
4. NEVER show the landing of a tossed/launched object when the next scene
   continues from it. The real failure: asked to show a bowl landing, H3
   featured a GIANT bowl in the foreground, and the next scene anchored on a
   full ramen bowl that re-manifested in his hands. Fix pattern: the object
   sails OUT OF FRAME in the first moment, the impact lives in the
   soundscape, the scene ends on the clean state you want to anchor on.
5. When a junction pops anyway: soften by re-rendering the downstream scene
   with its description opening "The shot opens exactly on the first frame:
   <restate the incoming state>" so the model treats the anchor as canon.
6. A scene is a narrative chunk with ONE job. If you cannot say what a scene
   is for in one sentence, split it.
