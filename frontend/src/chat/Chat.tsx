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

interface Props {
  onProjectChanged?: () => void;
  /** the operator's current asset selection — the agent's "this one" */
  selected?: { slug: string; path: string; group: string; labels: string[] }[] | null;
}

export function Chat({ onProjectChanged, selected }: Props) {
  const selectedRef = useRef(selected);
  selectedRef.current = selected;
  const [entries, setEntries] = useState<Entry[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [attachNote, setAttachNote] = useState<string | null>(null);
  const [sendSelection, setSendSelection] = useState(false);
  const fileInput = useRef<HTMLInputElement | null>(null);
  const history = useRef<{ role: string; content: string }[]>([]);
  const scroller = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => {
    inputRef.current?.focus();
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

  return (
    <div className="chat" data-testid="chat"
      onDragOver={(e) => { if (e.dataTransfer.types.includes("Files")) e.preventDefault(); }}
      onDrop={(e) => {
        if (e.dataTransfer.files.length === 0) return;
        e.preventDefault();
        void attach(e.dataTransfer.files);
      }}>
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
          ref={inputRef}
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
    </div>
  );
}
