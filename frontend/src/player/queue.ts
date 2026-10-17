/**
 * Sequential playback queue: plays scene clips back-to-back "as though
 * stitched" without concatenating anything. Pure logic — the React component
 * drives <video> elements from it.
 */

export interface Clip {
  id: string;
  url: string;
  durationS: number;
}

export interface QueueState {
  index: number;       // which clip is playing
  elapsedInClip: number; // seconds into the current clip
}

export function createQueue(clips: Clip[], startS = 0): QueueState {
  let t = startS;
  for (let i = 0; i < clips.length; i++) {
    if (t < clips[i].durationS - 1e-6) {
      return { index: i, elapsedInClip: t };
    }
    t -= clips[i].durationS;
  }
  return { index: Math.max(0, clips.length - 1), elapsedInClip: 0 };
}

/** The absolute reel time of the playhead. */
export function absoluteTime(clips: Clip[], state: QueueState): number {
  let t = state.elapsedInClip;
  for (let i = 0; i < state.index; i++) t += clips[i].durationS;
  return t;
}

/** Advance by dt across clip boundaries. Returns null when the reel ended. */
export function advance(clips: Clip[], state: QueueState, dt: number): QueueState | null {
  let index = state.index;
  let elapsed = state.elapsedInClip + dt;
  while (index < clips.length && elapsed >= clips[index].durationS - 1e-6) {
    elapsed -= clips[index].durationS;
    index++;
  }
  if (index >= clips.length) return null;
  return { index, elapsedInClip: elapsed };
}
