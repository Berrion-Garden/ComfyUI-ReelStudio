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

interface Props {
  onProjectChanged?: () => void;
  /** the operator's current asset selection — the agent's "this one" */
  selected?: { slug: string; path: string; group: string; labels: string[] }[] | null;
}

const GEOMETRY_KEY = "reelstudio.chat.geometry.v1";
const MIN_W = 280;
const MIN_H = 200;
const TITLE_H = 36;
const SNAP = 12;

const clamp = (v: number, lo: number, hi: number) => Math.min(Math.max(v, lo), hi);

/** Keep the window grabbable: ≥60px of the title bar and the whole bar in view. */
const fitToViewport = (g: Geometry, vw: number, vh: number): Geometry => {
  const w = clamp(g.w, MIN_W, vw);
  const h = clamp(g.h, MIN_H, vh);
  const x = clamp(g.x, -w + 60, vw - 60);
  const y = clamp(g.y, -h + TITLE_H, vh - TITLE_H);
  return { x, y, w, h };
};

/** First launch mirrors the old layout: a full-width strip along the bottom. */
const defaultGeometry = (vw: number, vh: number): Geometry =>
  fitToViewport({ x: 0, y: vh - 320, w: vw, h: 320 }, vw, vh);

const num = (n: unknown) =>
  typeof n === "number" && Number.isFinite(n) ? n : null;

const loadGeometry = (vw: number, vh: number): Geometry => {
  try {
    const raw = localStorage.getItem(GEOMETRY_KEY);
    if (!raw) return defaultGeometry(vw, vh);
    const p = JSON.parse(raw) as Record<string, unknown>;
    const x = num(p.x), y = num(p.y), w = num(p.w), h = num(p.h);
    if (x === null || y === null || w === null || h === null) {
      return defaultGeometry(vw, vh);
    }
    return fitToViewport({ x, y, w, h }, vw, vh);
  } catch {
    return defaultGeometry(vw, vh);
  }
};

/** Magnetic edges: release near a viewport edge and the window parks flush. */
const snapToEdges = (g: Geometry, vw: number, vh: number): Geometry => ({
  ...g,
  x: g.x < SNAP ? 0 : g.x + g.w > vw - SNAP ? vw - g.w : g.x,
  y: g.y < SNAP ? 0 : g.y + g.h > vh - SNAP ? vh - g.h : g.y,
});

const snapSize = (g: Geometry, vw: number, vh: number): Geometry => ({
  ...g,
  w: g.x + g.w > vw - SNAP ? Math.max(MIN_W, vw - g.x) : g.w,
  h: g.y + g.h > vh - SNAP ? Math.max(MIN_H, vh - g.y) : g.h,
});

export function FloatingChat({ onProjectChanged, selected }: Props) {
  const selectedRef = useRef(selected);
  selectedRef.current = selected;
  const [entries, setEntries] = useState<Entry[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [attachNote, setAttachNote] = useState<string | null>(null);
  const [sendSelection, setSendSelection] = useState(false);
  const [minimized, setMinimized] = useState(false);
  const [g, setG] = useState<Geometry>(() =>
    loadGeometry(window.innerWidth, window.innerHeight));
  const gRef = useRef(g);
  gRef.current = g;
  const fileInput = useRef<HTMLInputElement | null>(null);
  const history = useRef<{ role: string; content: string }[]>([]);
  const scroller = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    try { localStorage.setItem(GEOMETRY_KEY, JSON.stringify(g)); } catch { /* private mode */ }
  }, [g]);

  useEffect(() => {
    const onResize = () =>
      setG((s) => fitToViewport(s, window.innerWidth, window.innerHeight));
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  /** Upload files for the next message; images land in images/, audio in audio/. */
  const attach = async (files: FileList | File[]) => {
    const list = Array.from(files);
    if (list.length === 0) return;
    const audio = [".mp3", ".wav", ".ogg", ".flac", ".m4a"];
    setAttachNote(null);
    for (const f of list) {
      const dir = audio.some((e) => f.name.toLowerCase().endsWith(e))
        ? "audio" : "images";
      try {
        const ref = await uploadFile(f, dir);
        setAttachments((a) => [...a, { ref, name: f.name }]);
      } catch (e) {
        setAttachNote(`${f.name}: ${String(e)}`);
      }
    }
  };

  const scrollBottom = () => {
    requestAnimationFrame(() => {
      scroller.current?.scrollTo({ top: scroller.current.scrollHeight });
    });
  };

  const send = async () => {
    let message = input.trim();
    if ((!message && attachments.length === 0) || busy) return;
    if (attachments.length > 0) {
      // the agent's unique ids: `asset:<path>` resolves through get_assets
      message = `${message}\n[attached: ${attachments.map((a) => a.ref).join(" ")}]`;
    }
    setInput("");
    setAttachments([]);
    setBusy(true);
    setEntries((e) => [...e, { role: "user", text: message }]);
    scrollBottom();
    try {
      for await (const ev of chatStream(message, history.current,
                                         selectedRef.current, sendSelection)) {
        handleEvent(ev);
      }
    } catch (e) {
      setEntries((en) => [...en, { role: "agent", text: `⚠ ${String(e)}` }]);
    } finally {
      setBusy(false);
      scrollBottom();
    }
  };

  const handleEvent = (ev: ChatEvent) => {
    if (ev.type === "message") {
      setEntries((e) => [...e, { role: "agent", text: ev.text ?? "" }]);
      history.current.push({ role: "assistant", content: ev.text ?? "" });
    } else if (ev.type === "tool_call") {
      const args = ev.args as Record<string, unknown> | undefined;
      const summary = ev.name === "update_yaml" ? "updating reel.yaml"
        : ev.name === "generate"
          ? `generating ${(args?.kind as string | undefined) ?? "?"}${
              Array.isArray(args?.scene_ids) ? ` (${(args.scene_ids as string[]).join(", ")})`
              : args?.stale ? " (stale scenes)"
              : args?.name ? ` (${String(args.name)})` : ""}`
          : `${ev.name}`;
      setEntries((e) => [...e, { role: "tool", text: `⚙ ${summary}` }]);
    } else if (ev.type === "tool_result") {
      onProjectChanged?.();
    } else if (ev.type === "error") {
      setEntries((e) => [...e, { role: "agent", text: `⚠ ${ev.error}` }]);
    }
    scrollBottom();
  };

  /** Drag the window by its title bar; release near an edge parks it flush.
   *  The pointer offset stays OUT of the geometry state: spreading it into a
   *  setG value would bake stale coordinates in and clobber the next drag. */
  const startMove = (e: React.PointerEvent) => {
    if (e.button !== 0 || (e.target as HTMLElement).closest("button")) return;
    e.preventDefault();
    const g0 = { ...gRef.current };
    const sx = e.clientX, sy = e.clientY;
    const move = (ev: PointerEvent) => {
      setG(fitToViewport(
        { ...g0, x: g0.x + ev.clientX - sx, y: g0.y + ev.clientY - sy },
        window.innerWidth, window.innerHeight));
    };
    const up = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      window.removeEventListener("pointercancel", up);
      setG((cur) => snapToEdges(cur, window.innerWidth, window.innerHeight));
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
    window.addEventListener("pointercancel", up);
  };

  /** Grow/shrink from the bottom-right corner; near the edge it stretches flush. */
  const startResize = (e: React.PointerEvent) => {
    if (e.button !== 0) return;
    e.preventDefault();
    const g0 = { ...gRef.current };
    const sx = e.clientX, sy = e.clientY;
    const move = (ev: PointerEvent) => {
      const vw = window.innerWidth, vh = window.innerHeight;
      setG({
        ...g0,
        w: clamp(g0.w + ev.clientX - sx, MIN_W, Math.max(MIN_W, vw - g0.x)),
        h: clamp(g0.h + ev.clientY - sy, MIN_H, Math.max(MIN_H, vh - g0.y)),
      });
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
      window.innerWidth, window.innerHeight));
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
        void attach(e.dataTransfer.files);
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
          Agent{busy ? " · working…" : ""}
        </span>
        <button type="button" className="chat-float-min"
          aria-label={minimized ? "restore chat" : "minimize chat"}
          onClick={() => setMinimized((m) => !m)}>{minimized ? "+" : "–"}</button>
      </div>
      <div className="chat-log" ref={scroller} aria-live="polite">
        {entries.map((entry, i) => (
          <div key={i} className={`chat-entry role-${entry.role}`}>
            <span className="chat-role">{entry.role === "user" ? "you" : entry.role === "agent" ? "agent" : "…"}</span>
            <span className="chat-text">{entry.text}</span>
          </div>
        ))}
        {busy && <div className="chat-entry role-tool">…thinking</div>}
      </div>
      <div className="chat-attach">
        {attachments.map((a, i) => (
          <span key={`${a.ref}-${i}`} className="attach-chip" title={a.ref}>
            {a.name}
            <button type="button" aria-label={`remove ${a.name}`}
              onClick={() => setAttachments((at) => at.filter((_, j) => j !== i))}>✕</button>
          </span>
        ))}
        {attachNote && <span className="attach-error" onClick={() => setAttachNote(null)}>{attachNote}</span>}
        <button type="button" className="chat-paperclip" title="attach files"
          aria-label="attach files" onClick={() => fileInput.current?.click()}>📎</button>
      </div>
      <div className="chat-input">
        <textarea
          value={input}
          placeholder={busy ? "agent is working…" : "tell the agent what to change"}
          aria-label="message the agent"
          rows={2}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void send();
            }
          }}
          disabled={busy}
        />
        <div className="chat-actions">
          <button type="button" className={`chat-toggle ${sendSelection ? "on" : ""}`}
            title="selecting this will attach the currently selected elements to every request"
            aria-pressed={sendSelection} aria-label="send selection image"
            onClick={() => setSendSelection((v) => !v)}>🖼 sel</button>
          <button type="button" onClick={() => void send()} disabled={busy}>Send</button>
        </div>
      </div>
      <input ref={fileInput} type="file" multiple hidden
        onChange={(e) => {
          if (e.target.files?.length) void attach(e.target.files);
          e.target.value = "";
        }} />
      <div className="chat-float-resize" data-testid="floating-chat-resize"
        aria-hidden="true" onPointerDown={startResize} />
    </div>
  );
}
