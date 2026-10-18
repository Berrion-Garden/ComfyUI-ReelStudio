import { describe, expect, it } from "vitest";
import { spanCols, videoCell } from "./layout";
import type { SceneView } from "../types";

function scene(id: string, startS: number, durationS: number, partial: Partial<SceneView> = {}): SceneView {
  return {
    id, next: null, index: 0, mode: "i2v", frames: 107,
    duration_s: durationS, start_s: startS,
    first: { kind: "none" }, last: { kind: "none" },
    description: "", has_freeze: false, has_bell: false, bell_at: null, has_sfx: false,
    video_url: null, stale: false,
    ...partial,
  };
}

describe("videoCell", () => {
  it("missing without a render", () => {
    expect(videoCell(scene("s1", 0, 4))).toEqual({ kind: "missing" });
  });
  it("video vs stale-video", () => {
    const s = scene("s1", 0, 4, { video_url: "/v.mp4" });
    expect(videoCell(s).kind).toBe("video");
    expect(videoCell({ ...s, stale: true }).kind).toBe("stale-video");
  });
});

describe("spanCols", () => {
  const scenes = [
    scene("s1", 0, 4.46),
    scene("s2", 4.46, 1.88),
    scene("s3", 6.34, 4.46),
    scene("s4", 10.8, 4.46),
  ];
  it("a segment anchored at a scene start spans to the next anchor", () => {
    // opening: starts with s1, runs 6.34s → covers s1, s2 (ends at s3's start)
    expect(spanCols(scenes, 0, 6.34)).toEqual({ start: 1, end: 3 });
  });
  it("a segment running to the reel end spans to the last scene", () => {
    expect(spanCols(scenes, 6.34, 8.92)).toEqual({ start: 3, end: 5 });
  });
  it("degenerate zero-length span still lands in a column", () => {
    expect(spanCols(scenes, 4.46, 0)).toEqual({ start: 2, end: 3 });
  });
});
