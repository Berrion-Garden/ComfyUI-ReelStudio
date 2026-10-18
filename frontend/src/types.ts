export interface Anchor {
  kind: "none" | "prev_last" | "still" | "path";
  path?: string;
  ref?: string;
}

export interface SceneView {
  id: string;
  next: string | null;
  index: number;
  mode: string;
  frames: number;
  duration_s: number;
  first: Anchor;
  last: Anchor;
  description: string;
  has_freeze: boolean;
  has_bell: boolean;
  bell_at: number | null;
  has_sfx: boolean;
  video_url: string | null;
  stale: boolean;
  start_s: number;
}

export interface MusicView {
  name: string;
  start_s: number;
  duration_s: number;
  gain: number;
  stale: boolean;
  present: boolean;
  url: string | null;
}

/** A real-file `music_2` overlay — the audio the production mix actually uses. */
export interface OverlayView {
  name: string;
  index: number;
  start_s: number;
  duration_s: number;
  gain: number;
  seek: number;
  fades: [number, number][];
  present: boolean;
  url: string | null;
}

export interface JobView {
  id: string;
  kind: string;
  target: string;
  status: "queued" | "running" | "done" | "error";
  error: string | null;
  result: string | null;
}

export interface ProjectView {
  yaml_path: string;
  fps: number;
  width: number;
  height: number;
  total_s: number;
  final_path: string | null;
  flags: Record<string, unknown>;
  sfx_volume: [number, number][];
  scenes: SceneView[];
  music: MusicView[];
  overlays: OverlayView[];
  final_url: string | null;
  jobs: JobView[];
}

export interface ChatEvent {
  type: "message" | "tool_call" | "tool_result" | "error" | "done";
  text?: string;
  name?: string;
  args?: unknown;
  result?: string;
  error?: string;
}
