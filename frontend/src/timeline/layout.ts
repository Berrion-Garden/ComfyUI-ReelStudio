import type { SceneView } from "../types";

export interface Slice {
  id: string;
  startPct: number;
  widthPct: number;
  scene: SceneView;
}

/**
 * Horizontal slices: each scene's width is proportional to its on-screen
 * duration, positioned along the reel's total runtime.
 */
export function computeSlices(scenes: SceneView[], totalS: number): Slice[] {
  if (totalS <= 0) return [];
  return scenes.map((s) => ({
    id: s.id,
    startPct: (s.start_s / totalS) * 100,
    widthPct: (s.duration_s / totalS) * 100,
    scene: s,
  }));
}

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

/** Audio rows for a scene: its baked clip audio plus any anchored music. */
export interface AudioCell {
  label: string;
  url: string | null; // null = present in YAML but not rendered yet
}

export function audioRows(scene: SceneView, music: { name: string; start_s: number; duration_s: number; present: boolean }[]): AudioCell[] {
  const rows: AudioCell[] = [];
  if (scene.video_url) {
    rows.push({ label: "clip", url: scene.video_url });
  }
  for (const m of music) {
    // a segment anchored at this scene plays from here
    const anchoredHere =
      m.start_s >= scene.start_s - 1e-6 &&
      m.start_s < scene.start_s + scene.duration_s - 1e-6;
    if (anchoredHere) {
      rows.push({ label: `music: ${m.name}`, url: null });
    }
  }
  return rows;
}
