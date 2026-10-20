import { useEffect, useRef, useState } from "react";
import { chatStream, uploadFile } from "../api";
import type { ChatEvent } from "../types";

interface Entry {
  role: "user" | "agent" | "tool";
  text: string;
}

/** An uploaded file waiting to be referenced by the next message. */
interface Attachment {
  ref: string;
  name: string;
}

interface Geometry {
  x: number;
  y: number;
  w: number;
  h: number;
}

type HistoryEntry = { role: string; content: string };

/** One tab = one independent agent context: its own history, entries,
 *  attachments, and draft. */
interface Tab {
  id: number;
  /** auto-set from the first message sent in this context */
  title: string | null;
  entries: Entry[];
  attachments: Attachment[];
  attachNote: string | null;
  input: string;
  busy: boolean;
  sendSelection: boolean;
}

interface Props {
  onProjectChanged?: () => void;
  /** the operator's current asset selection — the agent's "this one" */
  selected?: { slug: string; path: string; group: string; labels: string[] }[] | null;
}

const GEOMETRY_KEY = "reelstudio.chat.geometry.v1";
const MINIMIZED_KEY = "reelstudio.chat.minimized.v1";
const MIN_W = 280;
const MIN_H = 200;
const TITLE_H = 36;
const SNAP = 12;

const clamp = (v: number, lo: number, hi: number) => Math.min(Math.max(v, lo), hi);

/** Keep the window grabbable: ≥60px of the title bar and the whole bar in view.
 *  `fitH` is the height that must stay in view — the full window normally,
 *  the title bar alone while minimized, so the bar can park anywhere even
 *  where the restored window would not fit. */
const fitToViewport = (g: Geometry, vw: number, vh: number, fitH = g.h): Geometry => {
  const w = clamp(g.w, MIN_W, vw);
  const h = clamp(g.h, MIN_H, vh);
  const x = clamp(g.x, -w + 60, vw - 60);
  const y = clamp(g.y, -Math.min(fitH, h) + TITLE_H, vh - TITLE_H);
  return { x, y, w, h };
};

/** First launch mirrors the old layout: a full-width strip along the bottom. */
const defaultGeometry = (vw: number, vh: number): Geometry =>
  fitToViewport({ x: 0, y: vh - 320, w: vw, h: 320 }, vw, vh);

const num = (n: unknown) =>
  typeof n === "number" && Number.isFinite(n) ? n : null;

const loadGeometry = (vw: number, vh: number, minimized: boolean): Geometry => {
  try {
    const raw = localStorage.getItem(GEOMETRY_KEY);
    if (!raw) return defaultGeometry(vw, vh);
    const p = JSON.parse(raw) as Record<string, unknown>;
    const x = num(p.x), y = num(p.y), w = num(p.w), h = num(p.h);
    if (x === null || y === null || w === null || h === null) {
      return defaultGeometry(vw, vh);
    }
    return fitToViewport({ x, y, w, h }, vw, vh, minimized ? TITLE_H : h);
  } catch {
    return defaultGeometry(vw, vh);
  }
};

const loadMinimized = (): boolean => {
  try { return localStorage.getItem(MINIMIZED_KEY) === "true"; }
  catch { return false; }
};

/** Magnetic edges: release near a viewport edge and the window (or just the
 *  bar while minimized) parks flush. */
const snapToEdges = (g: Geometry, vw: number, vh: number, fitH = g.h): Geometry => ({
  ...g,
  x: g.x < SNAP ? 0 : g.x + g.w > vw - SNAP ? vw - g.w : g.x,
  y: g.y < SNAP ? 0 : g.y + fitH > vh - SNAP ? vh - fitH : g.y,
});

/** Resize release: a right/bottom edge near the viewport edge stretches flush;
 *  a left/top edge within the margin docks to 0. The opposite edge keeps its
 *  position in both cases. */
const snapSize = (g: Geometry, vw: number, vh: number): Geometry => {
  let { x, y, w, h } = g;
  if (x + w > vw - SNAP) w = Math.max(MIN_W, vw - x);
  if (y + h > vh - SNAP) h = Math.max(MIN_H, vh - y);
  if (x < SNAP) { w = x + w; x = 0; }
  if (y < SNAP) { h = y + h; y = 0; }
  return fitToViewport({ x, y, w, h }, vw, vh);
};

const newTab = (id: number): Tab => ({
  id, title: null, entries: [], attachments: [], attachNote: null,
  input: "", busy: false, sendSelection: false,
});

type Corner = "nw" | "ne" | "sw" | "se";
const CORNERS: Corner[] = ["nw", "ne", "sw", "se"];

export function FloatingChat({ onProjectChanged, selected }: Props) {
  const selectedRef = useRef(selected);
  selectedRef.current = selected;
  const [tabs, setTabs] = useState<Tab[]>([newTab(1)]);
  const [activeId, setActiveId] = useState(1);
  const [minimized, setMinimized] = useState(loadMinimized);
  const [g, setG] = useState<Geometry>(() =>
    loadGeometry(window.innerWidth, window.innerHeight, minimized));
  const gRef = useRef(g);
  gRef.current = g;
  const minimizedRef = useRef(minimized);
  minimizedRef.current = minimized;
  const activeIdRef = useRef(activeId);
  activeIdRef.current = activeId;
  const fileInput = useRef<HTMLInputElement | null>(null);
  // the backend is stateless — every request carries the full history — so
  // each context's history lives here, keyed by tab id
  const histories = useRef<Map<number, HistoryEntry[]>>(new Map());
  const nextId = useRef(2);
  const scroller = useRef<HTMLDivElement | null>(null);

  const active = tabs.find((t) => t.id === activeId) ?? tabs[0];

  const historyFor = (id: number): HistoryEntry[] => {
    let h = histories.current.get(id);
    if (!h) histories.current.set(id, (h = []));
    return h;
  };

  const updateTab = (id: number, patch: (t: Tab) => Tab) =>
    setTabs((ts) => ts.map((t) => (t.id === id ? patch(t) : t)));

  const addTab = () => {
    const id = nextId.current++;
    setTabs((ts) => [...ts, newTab(id)]);
    setActiveId(id);
  };

  const closeTab = (id: number) => {
    if (tabs.length <= 1) return;
    const idx = tabs.findIndex((t) => t.id === id);
    const rest = tabs.filter((t) => t.id !== id);
    setTabs(rest);
    histories.current.delete(id);
    if (activeId === id) setActiveId(rest[Math.max(0, idx - 1)].id);
  };

  useEffect(() => {
    try { localStorage.setItem(GEOMETRY_KEY, JSON.stringify(g)); } catch { /* private mode */ }
  }, [g]);

  useEffect(() => {
    try { localStorage.setItem(MINIMIZED_KEY, JSON.stringify(minimized)); } catch { /* private mode */ }
  }, [minimized]);

  useEffect(() => {
    const onResize = () =>
      setG((s) => fitToViewport(s, window.innerWidth, window.innerHeight,
        minimizedRef.current ? TITLE_H : s.h));
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  /** Minimize re-fits so the bar is fully in view — it is then the only UI.
   *  Restoring needs no re-fit: a bar position always satisfies the
   *  full-window clamp. */
  const toggleMinimized = () => {
    const next = !minimized;
    setMinimized(next);
    if (next) setG((s) => fitToViewport(s, window.innerWidth, window.innerHeight, TITLE_H));
  };

  /** The shared scroller shows the active tab; land at its bottom. */
  const scrollBottom = () => {
    requestAnimationFrame(() => {
      // jsdom's Element has no scrollTo — keep the call optional
      scroller.current?.scrollTo?.({ top: scroller.current.scrollHeight });
    });
  };

  useEffect(() => { scrollBottom(); }, [activeId]);

  /** Upload files for the next message; images land in images/, audio in audio/. */
  const attach = async (tabId: number, files: FileList | File[]) => {
    const list = Array.from(files);
    if (list.length === 0) return;
    const audio = [".mp3", ".wav", ".ogg", ".flac", ".m4a"];
    updateTab(tabId, (t) => ({ ...t, attachNote: null }));
    for (const f of list) {
      const dir = audio.some((e) => f.name.toLowerCase().endsWith(e))
        ? "audio" : "images";
      try {
        const ref = await uploadFile(f, dir);
        updateTab(tabId, (t) => ({
          ...t, attachments: [...t.attachments, { ref, name: f.name }],
        }));
      } catch (e) {
        updateTab(tabId, (t) => ({ ...t, attachNote: `${f.name}: ${String(e)}` }));
      }
    }
  };

  const send = async (tabId: number) => {
    const tab = tabs.find((t) => t.id === tabId);
    if (!tab) return;
    let message = tab.input.trim();
    if ((!message && tab.attachments.length === 0) || tab.busy) return;
    if (tab.attachments.length > 0) {
      // the agent's unique ids: `asset:<path>` resolves through get_assets
      message = `${message}\n[attached: ${tab.attachments.map((a) => a.ref).join(" ")}]`;
    }
    const hist = historyFor(tabId);
    const first = tab.entries.length === 0;
    updateTab(tabId, (t) => ({
      ...t,
      input: "", attachments: [], busy: true,
      title: first && t.title === null ? message.slice(0, 32) : t.title,
      entries: [...t.entries, { role: "user", text: message }],
    }));
    scrollBottom();
    try {
      for await (const ev of chatStream(message, hist,
                                          selectedRef.current, tab.sendSelection)) {
        handleEvent(ev, tabId);
      }
    } catch (e) {
      updateTab(tabId, (t) => ({
        ...t, entries: [...t.entries, { role: "agent", text: `⚠ ${String(e)}` }],
      }));
    } finally {
      updateTab(tabId, (t) => ({ ...t, busy: false }));
      if (activeIdRef.current === tabId) scrollBottom();
    }
  };

  const handleEvent = (ev: ChatEvent, tabId: number) => {
    if (ev.type === "message") {
      updateTab(tabId, (t) => ({
        ...t, entries: [...t.entries, { role: "agent", text: ev.text ?? "" }],
      }));
      historyFor(tabId).push({ role: "assistant", content: ev.text ?? "" });
    } else if (ev.type === "tool_call") {
      const args = ev.args as Record<string, unknown> | undefined;
      const summary = ev.name === "update_yaml" ? "updating reel.yaml"
        : ev.name === "generate"
          ? `generating ${(args?.kind as string | undefined) ?? "?"}${
              Array.isArray(args?.scene_ids) ? ` (${(args.scene_ids as string[]).join(", ")})`
              : args?.stale ? " (stale scenes)"
              : args?.name ? ` (${String(args.name)})` : ""}`
          : `${ev.name}`;
      updateTab(tabId, (t) => ({
        ...t, entries: [...t.entries, { role: "tool", text: `⚙ ${summary}` }],
      }));
    } else if (ev.type === "tool_result") {
      onProjectChanged?.();
    } else if (ev.type === "error") {
      updateTab(tabId, (t) => ({
        ...t, entries: [...t.entries, { role: "agent", text: `⚠ ${ev.error}` }],
      }));
    }
    if (activeIdRef.current === tabId) scrollBottom();
  };

  /** Drag the window by its title bar; release near an edge parks it flush.
   *  The pointer offset stays OUT of the geometry state: spreading it into a
   *  setG value would bake stale coordinates in and clobber the next drag. */
  const startMove = (e: React.PointerEvent) => {
    if (e.button !== 0 || (e.target as HTMLElement).closest("button")) return;
    e.preventDefault();
    const g0 = { ...gRef.current };
    // while minimized only the bar has to stay in view — the invisible body
    // of the restored window must not push it around
    const fitH = minimized ? TITLE_H : g0.h;
    const sx = e.clientX, sy = e.clientY;
    const move = (ev: PointerEvent) => {
      setG(fitToViewport(
        { ...g0, x: g0.x + ev.clientX - sx, y: g0.y + ev.clientY - sy },
        window.innerWidth, window.innerHeight, fitH));
    };
    const up = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      window.removeEventListener("pointercancel", up);
      setG((cur) => snapToEdges(cur, window.innerWidth, window.innerHeight, fitH));
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
    window.addEventListener("pointercancel", up);
  };

  /** Grow/shrink from any corner: the drag delta moves the corner's two edges
   *  while the opposite corner stays put; near an edge it docks flush. */
  const startResize = (corner: Corner) => (e: React.PointerEvent) => {
    if (e.button !== 0) return;
    e.preventDefault();
    const g0 = { ...gRef.current };
    const sx = e.clientX, sy = e.clientY;
    const right = g0.x + g0.w, bottom = g0.y + g0.h;
    const move = (ev: PointerEvent) => {
      const dx = ev.clientX - sx, dy = ev.clientY - sy;
      const vw = window.innerWidth, vh = window.innerHeight;
      let { x, y, w, h } = g0;
      if (corner === "se" || corner === "ne")
        w = clamp(g0.w + dx, MIN_W, Math.max(MIN_W, vw - g0.x));
      if (corner === "sw" || corner === "nw") {
        w = clamp(g0.w - dx, MIN_W, right);
        x = right - w;
      }
      if (corner === "se" || corner === "sw")
        h = clamp(g0.h + dy, MIN_H, Math.max(MIN_H, vh - g0.y));
      if (corner === "ne" || corner === "nw") {
        h = clamp(g0.h - dy, MIN_H, bottom);
        y = bottom - h;
      }
      setG(fitToViewport({ x, y, w, h }, vw, vh));
    };
    const up = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      window.removeEventListener("pointercancel", up);
      setG((cur) => snapSize(cur, window.innerWidth, window.innerHeight));
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
    window.addEventListener("pointercancel", up);
  };

  /** Arrow keys move the window so the drag is keyboard-reachable. */
  const nudge = (e: React.KeyboardEvent) => {
    const step = e.shiftKey ? 50 : 10;
    let dx = 0, dy = 0;
    if (e.key === "ArrowLeft") dx = -step;
    else if (e.key === "ArrowRight") dx = step;
    else if (e.key === "ArrowUp") dy = -step;
    else if (e.key === "ArrowDown") dy = step;
    else return;
    e.preventDefault();
    setG((cur) => fitToViewport(
      { ...cur, x: cur.x + dx, y: cur.y + dy },
      window.innerWidth, window.innerHeight,
      minimized ? TITLE_H : cur.h));
  };

  return (
    <div
      className={`chat-float${minimized ? " min" : ""}`}
      data-testid="floating-chat"
      style={{ left: g.x, top: g.y, width: g.w, height: minimized ? TITLE_H : g.h }}
      onDragOver={(e) => { if (e.dataTransfer.types.includes("Files")) e.preventDefault(); }}
      onDrop={(e) => {
        if (e.dataTransfer.files.length === 0) return;
        e.preventDefault();
        void attach(active.id, e.dataTransfer.files);
      }}>
      <div
        className="chat-float-title"
        tabIndex={0}
        title="drag to move, arrow keys to nudge"
        aria-label={minimized ? "agent chat window, minimized — drag or arrow keys to move"
                              : "agent chat window — drag or arrow keys to move"}
        onPointerDown={startMove}
        onKeyDown={nudge}>
        <span className="chat-float-title-text">
          Agent{active.busy ? " · working…" : ""}
        </span>
        <button type="button" className="chat-float-min"
          aria-label={minimized ? "restore chat" : "minimize chat"}
          onClick={toggleMinimized}>{minimized ? "+" : "–"}</button>
      </div>
      <div className="chat-tabs" role="tablist" aria-label="chat sessions">
        {tabs.map((t) => (
          <div key={t.id} role="tab" aria-selected={t.id === active.id}
            className={`chat-tab${t.id === active.id ? " on" : ""}`}
            title={t.title ?? `session ${t.id}`}
            onClick={() => setActiveId(t.id)}>
            <span className="chat-tab-name">{t.title ?? t.id}</span>
            {t.busy && t.id !== active.id && <span className="chat-tab-busy">●</span>}
            {tabs.length > 1 && (
              <button type="button" className="chat-tab-close"
                aria-label={`close session ${t.id}`}
                onClick={(e) => { e.stopPropagation(); closeTab(t.id); }}>✕</button>
            )}
          </div>
        ))}
        <button type="button" className="chat-tab-add"
          title="new session — a fresh context for the agent"
          aria-label="new chat session" onClick={addTab}>+</button>
      </div>
      <div className="chat-log" ref={scroller} aria-live="polite">
        {active.entries.map((entry, i) => (
          <div key={i} className={`chat-entry role-${entry.role}`}>
            <span className="chat-role">{entry.role === "user" ? "you" : entry.role === "agent" ? "agent" : "…"}</span>
            <span className="chat-text">{entry.text}</span>
          </div>
        ))}
        {active.busy && <div className="chat-entry role-tool">…thinking</div>}
      </div>
      <div className="chat-attach">
        {active.attachments.map((a, i) => (
          <span key={`${a.ref}-${i}`} className="attach-chip" title={a.ref}>
            {a.name}
            <button type="button" aria-label={`remove ${a.name}`}
              onClick={() => updateTab(active.id,
                (t) => ({ ...t, attachments: t.attachments.filter((_, j) => j !== i) }))}>✕</button>
          </span>
        ))}
        {active.attachNote && (
          <span className="attach-error"
            onClick={() => updateTab(active.id, (t) => ({ ...t, attachNote: null }))}>
            {active.attachNote}
          </span>
        )}
        <button type="button" className="chat-paperclip" title="attach files"
          aria-label="attach files" onClick={() => fileInput.current?.click()}>📎</button>
      </div>
      <div className="chat-input">
        <textarea
          value={active.input}
          placeholder={active.busy ? "agent is working…" : "tell the agent what to change"}
          aria-label="message the agent"
          rows={2}
          onChange={(e) => updateTab(active.id, (t) => ({ ...t, input: e.target.value }))}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void send(active.id);
            }
          }}
          disabled={active.busy}
        />
        <div className="chat-actions">
          <button type="button"
            className={`chat-toggle ${active.sendSelection ? "on" : ""}`}
            title="selecting this will attach the currently selected elements to every request"
            aria-pressed={active.sendSelection} aria-label="send selection image"
            onClick={() => updateTab(active.id,
              (t) => ({ ...t, sendSelection: !t.sendSelection }))}>🖼 sel</button>
          <button type="button" onClick={() => void send(active.id)}
            disabled={active.busy}>Send</button>
        </div>
      </div>
      <input ref={fileInput} type="file" multiple hidden
        onChange={(e) => {
          if (e.target.files?.length) void attach(active.id, e.target.files);
          e.target.value = "";
        }} />
      {CORNERS.map((c) => (
        <div key={c}
          className={`chat-float-resize chat-float-resize-${c}`}
          data-testid={c === "se" ? "floating-chat-resize" : `floating-chat-resize-${c}`}
          aria-hidden="true" onPointerDown={startResize(c)} />
      ))}
    </div>
  );
}
