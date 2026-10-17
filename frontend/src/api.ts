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

export async function renderStale(): Promise<void> {
  const resp = await fetch(`${API}/render`, {
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

export function finalUrl(): string | null {
  return `${API}/final`;
}

/** POST a chat message; yields SSE events as they stream. */
export async function* chatStream(
  message: string,
  history: { role: string; content: string }[],
): AsyncGenerator<ChatEvent> {
  const resp = await fetch(`${API}/agent/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, history }),
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
