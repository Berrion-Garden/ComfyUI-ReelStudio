import type { ChatEvent, ProjectView } from "./types";

const API = "/reelstudio/api";

async function json_or_throw<T>(resp: Response): Promise<T> {
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({ error: resp.statusText }));
    throw new Error((body as { error?: string }).error ?? `HTTP ${resp.status}`);
  }
  return (await resp.json()) as T;
}

export async function fetchProject(): Promise<ProjectView> {
  const resp = await fetch(`${API}/project`);
  return json_or_throw<ProjectView>(resp);
}

export async function renderScenes(sceneIds: string[]): Promise<void> {
  const resp = await fetch(`${API}/render`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ scene_ids: sceneIds }),
  });
  await json_or_throw(resp);
}

export async function renderStale(): Promise<void> {  const resp = await fetch(`${API}/render`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ stale: true }),
  });
  await json_or_throw(resp);
}

export async function assemble(useMusic: boolean): Promise<void> {
  const resp = await fetch(`${API}/assemble`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ use_music: useMusic }),
  });
  await json_or_throw(resp);
}

export function sceneArtifactUrl(sceneId: string, kind: string): string {
  return `${API}/scene/${sceneId}/artifact/${kind}`;
}

export function audioTrackUrl(index: number): string {
  return `${API}/audio/${index}/artifact`;
}

export function bellUrl(): string {
  return `${API}/bell/artifact`;
}

export interface SfxAssetEvent {
  asset: string;
  at: number;
  gain: number;
  url: string | null;
}

export interface SfxScene {
  id: string;
  soundscape: string;
  bell: string | boolean | null;
  bell_at: number | null;
  split: string | null;
  peaks: number[] | null;
  assets: SfxAssetEvent[];
}

export async function fetchSfxBoard(buckets = 0): Promise<SfxScene[]> {
  const resp = await fetch(`${API}/sfx/board?peaks=${buckets}`);
  return json_or_throw<{ scenes: SfxScene[] }>(resp).then((j) => j.scenes);
}

export async function placeSfxEvent(
  sceneId: string, asset: string, at: number, gain = 0.6,
): Promise<void> {
  const resp = await fetch(`${API}/sfx/board`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ scene_id: sceneId, asset, at, gain }),
  });
  await json_or_throw(resp);
}

export async function removeSfxEvent(
  sceneId: string, index: number,
): Promise<void> {
  const resp = await fetch(`${API}/sfx/board`, {
    method: "DELETE",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ scene_id: sceneId, index }),
  });
  await json_or_throw(resp);
}

export async function fetchAudioPeaks(index: number, buckets = 600): Promise<number[]> {
  const resp = await fetch(`${API}/audio/${index}/peaks?buckets=${buckets}`);
  const body = await json_or_throw<{ peaks: number[] }>(resp);
  return body.peaks;
}

export async function updateAudioTrack(
  index: number,
  patch: { at?: number; seek?: number; gain?: number; fades?: [number, number][] },
): Promise<void> {
  const resp = await fetch(`${API}/audio/${index}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
  await json_or_throw(resp);
}

export function finalUrl(): string | null {
  return `${API}/final`;
}

export interface AssetItem {
  path: string;
  slug: string;
  group: "characters" | "scenes" | "stills" | "custom" | "backgrounds"
    | "themes" | "audio" | "sfx";
  labels: string[];
  used_by: string[];
  url: string;
}

export interface AssetsData {
  groups: Record<AssetItem["group"], AssetItem[]>;
}

export async function fetchAssets(): Promise<AssetsData> {
  const resp = await fetch(`${API}/assets`);
  return json_or_throw<AssetsData>(resp);
}

/** Rewrite one asset's declared labels in the workspace assets.yaml. */
export async function setAssetLabels(path: string, labels: string[]): Promise<void> {
  const resp = await fetch(`${API}/assets/labels`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path, labels }),
  });
  await json_or_throw(resp);
}

/** Delete an asset (the operator's ✗ or the card ⋯ menu). */
export async function deleteAsset(path: string): Promise<void> {
  const resp = await fetch(`${API}/asset`, {
    method: "DELETE",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path }),
  });
  await json_or_throw(resp);
}

// ------------------------------------------------------------- studio ----

export interface StudioScene {
  slug: string;
  title: string;
  dir: string;
  current: boolean;
  characters: string[];
  backgrounds: string[];
}

export interface ImportSpec {
  from: string;
  characters: string[];
  backgrounds: string[];
  as?: string;
}

export interface StudioView {
  title: string;
  current: string;
  saved: boolean;
  workspace: string;
  scenes: StudioScene[];
}

export async function fetchStudio(): Promise<StudioView> {
  const resp = await fetch(`${API}/studio`);
  return json_or_throw(resp);
}

async function postStudio(path: string, body: object): Promise<StudioView> {
  const resp = await fetch(`${API}/studio${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return json_or_throw(resp);
}

export function saveScene(slug?: string, title?: string): Promise<StudioView> {
  return postStudio("/save", { slug, title });
}

export function openScene(slug: string): Promise<StudioView> {
  return postStudio("/open", { slug });
}

/** New scene from its name alone — the backend derives the slug
 * (snake_case + timestamp). `imp` optionally brings pools over from
 * another scene. */
export function newScene(title: string, imp?: ImportSpec): Promise<StudioView> {
  return postStudio("/scenes", { title, import: imp });
}

/** Copy character/location pools from another scene into the current one. */
export async function importAssets(spec: ImportSpec): Promise<void> {
  const resp = await fetch(`${API}/studio/import`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(spec),
  });
  await json_or_throw(resp);
}

/** Upload one file into a workspace library dir (the studio's paperclip,
 * section + and drag-and-drop anchors). Returns the asset:<path> ref. */
export async function uploadFile(file: File, dir: string): Promise<string> {
  const form = new FormData();
  form.append("file", file);
  const resp = await fetch(`${API}/upload?dir=${encodeURIComponent(dir)}`, {
    method: "POST",
    body: form,
  });
  const body = await json_or_throw<{ path: string }>(resp);
  return `asset:${body.path}`;
}

/** Grab a reference track off the web (YouTube, …) into audio/. */
export async function importAudioFromUrl(url: string, name?: string): Promise<void> {
  const resp = await fetch(`${API}/audio/import`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url, ...(name ? { name } : {}) }),
  });
  await json_or_throw(resp);
}

/** How one generated file was made: its job, the request context, and the
 * prompt/seed/models embedded in the file (images). */
export interface Provenance {
  file: string;
  job: string | null;
  record: { id: string; kind: string; target: string; args: Record<string, unknown>;
            status: string; result?: string; seed?: string | null; ts: number } | null;
  embedded: Record<string, string | number> | null;
}

export async function getProvenance(path: string): Promise<Provenance> {
  const resp = await fetch(`${API}/provenance?path=${encodeURIComponent(path)}`);
  return json_or_throw<Provenance>(resp);
}

/** Declare renders current — the whole reel or one scene (thumbnail ✓). */
export async function adoptScene(sceneId?: string): Promise<void> {
  const resp = await fetch(`${API}/manifest/adopt`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(sceneId ? { scene_id: sceneId } : {}),
  });
  await json_or_throw(resp);
}

/** POST a chat message; yields SSE events as they stream. */
export async function* chatStream(
  message: string,
  history: { role: string; content: string }[],
  selected?: { slug: string; path: string; group: string; labels: string[] }[] | null,
  attachSelection?: boolean,
): AsyncGenerator<ChatEvent> {
  const resp = await fetch(`${API}/agent/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message, history, selected: selected ?? null,
      attach_selection: attachSelection ?? false,
    }),
  });
  if (!resp.ok || !resp.body) {
    throw new Error(`chat failed: HTTP ${resp.status}`);
  }
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let idx: number;
    while ((idx = buffer.indexOf("\n\n")) >= 0) {
      const chunk = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      for (const line of chunk.split("\n")) {
        if (line.startsWith("data: ")) {
          yield JSON.parse(line.slice(6)) as ChatEvent;
        }
      }
    }
  }
}
