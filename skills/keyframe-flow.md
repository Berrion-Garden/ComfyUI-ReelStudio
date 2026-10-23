---
name: keyframe-flow
description: >
  Keyframe-pair flow doctrine — how two anchor stills decide whether a
  segment reads as motion or as a morph. Master plates for environment and
  camera beats, end-to-start composition for action chains, joint-flow
  judging, and the canon wardrobe gate. Always on.
always: true
---

# Keyframe flow: the anchors decide the motion

H3 does not "pan across a space" or "track a character". It animates from
keyframe A to keyframe B, and everything the model does is make A into B.
So whether a segment flows is decided at the ANCHORS, before any prompt:
A and B must be the same world with the camera or the character moved —
not two separate generations of roughly the same idea.

## The three pair designs

1. **Master plate + crop keyframes (camera moves / establishing beats).**
   When a script beat wants a pan, a push-in, or a sweep across a location:
   generate ONE wide master plate of the location at plate resolution
   (single image, no character unless the beat needs him mid-pan), then the
   segment's first and last anchors are CROPS OF THAT PLATE at the camera
   positions. Never two separately prompted wides — the model will reshape
   the environment (walls grow, clocks migrate) and the beat reads as
   nonsense. One plate per location per beat; the plate IS the location.
2. **Same-composition pairs (single camera, single subject).**
   For a beat inside one setup: design both keyframes together — same
   framing scale, same environment, same light; the only delta is the
   subject's pose or the camera's framing.
3. **End-to-start chains (multi-segment actions).**
   A continuous action broken across segments composes end-to-start:
   design segment N's LAST frame as segment N+1's FIRST. Not merely
   "file-identical at the joint" — the composition must carry the action
   (a segment ending kneeling at the sarcophagus does not hand off to one
   opening sitting cross-legged on the floor: that is a jump, and a jump
   inside one continuous beat is a fault even when the anchor file is the
   same).

## Cuts are the boundary of a shot

A hard cut between segments is correct exactly where the script's own
prompts change the camera setup (a new prompt is a new shot). Within one
script prompt, the segments must flow — if they cut or morph, the anchor
design is wrong, not the video render.

## Judge the JOINTS, not just the leaves

A leaf judged alone (wardrobe, identity, pose) can pass while its chain
fails. Before picking an anchor, view the frames on BOTH sides of every
joint it will join (view_frames on the neighboring segments if they are
rendered; compare the candidate against its neighbors' end frames). The
pass bar for a pick is three gates:
1. **canon**: wardrobe, identity, palette per the character block — no
   invented garments (a gakuran is a high standing collar, never a hood);
2. **beat**: the pose serves the beat's text;
3. **flow**: the composition hands the action or the camera to the next
   keyframe the way the shot needs.

## Editing discipline

Edit at the owning layer (narrative beats in storyboard.yaml, pose
directives in the shot, anchors in imagery — never negatives; junction
doctrine anchors state in frames). After an anchor change, re-render the
segments it feeds — the staleness marks them; render upstream-first in one
pass so the chain resolves frame-exact.
