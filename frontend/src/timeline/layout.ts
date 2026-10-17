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
