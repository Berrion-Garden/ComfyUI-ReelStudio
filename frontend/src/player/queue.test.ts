import { describe, expect, it } from "vitest";
import { absoluteTime, advance, createQueue, type Clip } from "./queue";

const clips: Clip[] = [
  { id: "s1", url: "/a.mp4", durationS: 2 },
  { id: "s2", url: "/b.mp4", durationS: 3 },
  { id: "s3", url: "/c.mp4", durationS: 1.5 },
];

describe("createQueue", () => {
  it("starts at the first clip", () => {
    expect(createQueue(clips)).toEqual({ index: 0, elapsedInClip: 0 });
  });

  it("can start mid-reel (seek)", () => {
    expect(createQueue(clips, 2.5)).toEqual({ index: 1, elapsedInClip: 0.5 });
  });
});

describe("advance", () => {
  it("stays inside a clip", () => {
    expect(advance(clips, { index: 0, elapsedInClip: 1 }, 0.5))
      .toEqual({ index: 0, elapsedInClip: 1.5 });
  });

  it("crosses a boundary without losing time", () => {
    expect(advance(clips, { index: 0, elapsedInClip: 1.75 }, 0.5))
      .toEqual({ index: 1, elapsedInClip: 0.25 });
  });

  it("crosses several boundaries in one step (frame drops)", () => {
    expect(advance(clips, { index: 0, elapsedInClip: 0 }, 4))
      .toEqual({ index: 1, elapsedInClip: 2 });
  });

  it("returns null at the end of the reel", () => {
    expect(advance(clips, { index: 2, elapsedInClip: 1.4 }, 0.2)).toBeNull();
  });
});

describe("absoluteTime", () => {
  it("sums upstream clips plus in-clip elapsed", () => {
    expect(absoluteTime(clips, { index: 2, elapsedInClip: 0.5 })).toBe(5.5);
    expect(absoluteTime(clips, { index: 0, elapsedInClip: 0.25 })).toBe(0.25);
  });
});
