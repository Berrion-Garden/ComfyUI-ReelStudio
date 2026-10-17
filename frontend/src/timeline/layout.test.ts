import { describe, expect, it } from "vitest";
import { audioRows, computeSlices, videoCell } from "./layout";
import type { SceneView } from "../types";

function scene(partial: Partial<SceneView>): SceneView {
  return {
    id: "s1",
    next: null,
    index: 0,
    mode: "i2v",
    frames: 107,
    duration_s: 4.4583,
    first: { kind: "none" },
    last: { kind: "none" },
    description: "",
    has_freeze: false,
    has_bell: false,
    video_url: null,
    stale: true,
    start_s: 0,
    ...partial,
  };
}

describe("computeSlices", () => {
  it("widths are proportional to on-screen duration", () => {
    const scenes = [
      scene({ id: "a", start_s: 0, duration_s: 2 }),
      scene({ id: "b", start_s: 2, duration_s: 6 }),
    ];
    const slices = computeSlices(scenes, 8);
    expect(slices[0].widthPct).toBeCloseTo(25);
    expect(slices[1].widthPct).toBeCloseTo(75);
    expect(slices[1].startPct).toBeCloseTo(25);
  });

  it("a short scene gets a proportionally narrow slice, not a fixed one", () => {
    const scenes = [
      scene({ id: "a", start_s: 0, duration_s: 1.9 }),
      scene({ id: "b", start_s: 1.9, duration_s: 3.33 }),
    ];
    const slices = computeSlices(scenes, 5.23);
    expect(slices[0].widthPct).toBeCloseTo((1.9 / 5.23) * 100, 5);
  });

  it("handles empty timeline", () => {
    expect(computeSlices([], 0)).toEqual([]);
  });
});

describe("videoCell", () => {
  it("XXX when no render exists", () => {
    expect(videoCell(scene({})).kind).toBe("missing");
  });

  it("stale flag marks a rendered scene as stale-video", () => {
    expect(videoCell(scene({ video_url: "/v.mp4", stale: true })).kind).toBe("stale-video");
    expect(videoCell(scene({ video_url: "/v.mp4", stale: false })).kind).toBe("video");
  });
});

describe("audioRows", () => {
  it("baked clip audio row only when rendered", () => {
    expect(audioRows(scene({}), [])).toEqual([]);
    expect(audioRows(scene({ video_url: "/v.mp4" }), []))
      .toEqual([{ label: "clip", url: "/v.mp4" }]);
  });

  it("music segment anchored at the scene appears as a row", () => {
    const music = [{ name: "battle", start_s: 4.46, duration_s: 13, present: false }];    const s2 = scene({ id: "s2", start_s: 4.46, duration_s: 3.33 });
    const rows = audioRows(s2, music);
    expect(rows).toEqual([
      { label: "music: battle", url: null },  // not rendered yet
    ]);
  });

  it("a music segment anchored elsewhere does not appear", () => {
    const music = [{ name: "battle", start_s: 0, duration_s: 4.4, present: true }];
    expect(audioRows(scene({ id: "s9", start_s: 10, duration_s: 3 }), music)).toEqual([]);
  });
});
