/**
 * The on-the-fly preview mix — the same layers the real mix applies:
 * baked clip audio under the sfx envelope (ducked when music is in),
 * audio tracks at their `seek` offset with gain × fades envelopes, bell
 * one-shots, and the 1.2 s master fade. Pure math so the schedule is
 * testable without media elements.
 */

export interface MixSource {
  key: string;
  url: string;
  /** absolute video-time start */
  startS: number;
  durS: number;
  gain: number;
  /** start offset into the source file */
  seek: number;
  /** absolute video-time [second, volume] keyframes */
  fades: [number, number][];
}

export interface TrackPlan {
  key: string;
  active: boolean;
  /** position in the SOURCE file (seek + elapsed into the span) */
  offset: number;
  volume: number;
}

const clamp01 = (v: number) => Math.min(1, Math.max(0, v));

/** Linear-interpolated volume at video-time t over keyframes, held before
 * the first / after the last — mirrors reel.py's vol_curve. */
export function envAt(fades: [number, number][], t: number): number {
  if (fades.length === 0) return 1;
  if (t <= fades[0][0]) return fades[0][1];
  for (let i = 1; i < fades.length; i++) {
    if (t <= fades[i][0]) {
      const [t0, v0] = fades[i - 1];
      const [t1, v1] = fades[i];
      return t1 === t0 ? v1 : v0 + (v1 - v0) * ((t - t0) / (t1 - t0));
    }
  }
  return fades[fades.length - 1][1];
}

/** Gentle 1.2 s fade at the very end of the reel, like the master mix. */
export function fadeOut(t: number, totalS: number, d = 1.2): number {
  return totalS > 0 && t > totalS - d ? clamp01((totalS - t) / d) : 1;
}

/** What every source track should be doing at playhead t. */
export function trackPlans(
  sources: MixSource[],
  t: number,
  totalS: number,
): TrackPlan[] {
  const master = fadeOut(t, totalS);
  return sources.map((s) => {
    const inSpan = t >= s.startS - 1e-6 && t < s.startS + s.durS - 1e-6;
    return {
      key: s.key,
      active: inSpan,
      offset: Math.max(0, s.seek) + (t - s.startS),
      volume: clamp01(s.gain * envAt(s.fades, t) * master),
    };
  });
}

/** Volume automation for the baked scene audio, ducked when music is in. */
export function sfxVolumeAt(
  sfxVolume: [number, number][],
  t: number,
  totalS: number,
  useMusic: boolean,
): number {
  return clamp01(envAt(sfxVolume, t) * (useMusic ? 0.45 : 1.0) * fadeOut(t, totalS));
}

/** Absolute reel times of the synth bell one-shots. */
export function bellTimes(scenes: { start_s: number; bell_at: number | null }[]): number[] {
  return scenes
    .filter((s) => s.bell_at !== null)
    .map((s) => s.start_s + (s.bell_at as number));
}
