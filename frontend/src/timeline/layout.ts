import type { SceneView } from "../types";

export type Cell =
  | { kind: "video"; url: string }
  | { kind: "missing" }
  | { kind: "stale-video"; url: string };

export function videoCell(scene: SceneView): Cell {
  if (!scene.video_url) return { kind: "missing" };
  return scene.stale
    ? { kind: "stale-video", url: scene.video_url }
    : { kind: "video", url: scene.video_url };
}

/** Grid line span (1-based, inclusive-exclusive) of a time span over scenes. */
export function spanCols(scenes: SceneView[], startS: number, durationS: number) {
  let first = scenes.findIndex((s) => s.start_s + s.duration_s > startS + 1e-6);
  if (first === -1) first = 0;
  let last = first;
  for (let i = first; i < scenes.length; i++) {
    if (scenes[i].start_s < startS + durationS - 1e-6) last = i;
  }
  return { start: first + 1, end: last + 2 };
}
