import { describe, expect, it } from "vitest";
import { bellTimes, envAt, fadeOut, sfxVolumeAt, trackPlans } from "./mix";
import type { MixSource } from "./mix";

const src = (partial: Partial<MixSource> = {}): MixSource => ({
  key: "a0", url: "/t.mp3", startS: 10, durS: 20,
  gain: 1, seek: 0, fades: [], ...partial,
});

describe("envAt — the yaml's volume envelope", () => {
  const fades: [number, number][] = [[15, 0.1], [18, 1.0], [35, 0.5]];

  it("holds the first keyframe before the envelope starts", () => {
    expect(envAt(fades, 0)).toBe(0.1);
    expect(envAt(fades, 15)).toBe(0.1);
  });

  it("interpolates linearly between keyframes", () => {
    expect(envAt(fades, 16.5)).toBeCloseTo(0.55);
  });

  it("holds the last keyframe after the envelope ends", () => {
    expect(envAt(fades, 40)).toBe(0.5);
  });

  it("no keyframes means full volume", () => {
    expect(envAt([], 3)).toBe(1);
  });
});

describe("trackPlans — what every source should be doing", () => {
  it("activates a source inside its span, at seek + elapsed", () => {
    const plans = trackPlans([src({ seek: 90 })], 12, 45);
    expect(plans[0].active).toBe(true);
    expect(plans[0].offset).toBe(92); // 90 + 2s in
  });

  it("deactivates outside the span and at the very end", () => {
    const plans = trackPlans([src()], 5, 45);
    expect(plans[0].active).toBe(false);
    expect(trackPlans([src()], 30, 45)[0].active).toBe(false); // start 10 + dur 20
  });

  it("volume is gain × envelope × master fade", () => {
    const plans = trackPlans(
      [src({ gain: 0.5, fades: [[0, 0], [45, 1]] })], 22.5, 45);
    expect(plans[0].volume).toBeCloseTo(0.25); // 0.5 × 0.5 × fade(1.0 here)
  });

  it("the master fade silences everything at the reel end", () => {
    expect(trackPlans([src({ startS: 0, durS: 45 })], 45, 45)[0].volume).toBe(0);
    const near = trackPlans([src({ startS: 0, durS: 45 })], 44.4, 45)[0];
    expect(near.volume).toBeCloseTo(0.5); // (45 - 44.4) / 1.2
  });
});

describe("sfxVolumeAt — baked clip audio automation", () => {
  it("is silent before the first keyframe", () => {
    expect(sfxVolumeAt([[25.5, 0], [26, 1]], 10, 45, false)).toBe(0);
  });

  it("ducks to 45% when music is in the mix", () => {
    expect(sfxVolumeAt([[0, 1]], 10, 45, true)).toBeCloseTo(0.45);
    expect(sfxVolumeAt([[0, 1]], 10, 45, false)).toBe(1);
  });
});

describe("fadeOut and bellTimes", () => {
  it("fades only over the last 1.2s", () => {
    expect(fadeOut(40, 45)).toBe(1);
    expect(fadeOut(44.4, 45)).toBeCloseTo(0.5);
  });

  it("bell one-shots land at scene start + bell_at", () => {
    expect(bellTimes([
      { start_s: 0, bell_at: null },
      { start_s: 30.25, bell_at: 1.79 },
    ])).toEqual([32.04]);
  });
});
