import { useEffect, useRef, useState } from "react";
import { chatStream } from "../api";
import type { ChatEvent } from "../types";

interface Entry {
  role: "user" | "agent" | "tool";
  text: string;
}

interface Props {
  onProjectChanged?: () => void;
  /** the operator's current asset selection — the agent's "this one" */
  selected?: { slug: string; path: string; group: string; labels: string[] } | null;
}

export function Chat({ onProjectChanged, selected }: Props) {
  const selectedRef = useRef(selected);
  selectedRef.current = selected;
  const [entries, setEntries] = useState<Entry[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const history = useRef<{ role: string; content: string }[]>([]);
  const scroller = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const scrollBottom = () => {
    requestAnimationFrame(() => {
      scroller.current?.scrollTo({ top: scroller.current.scrollHeight });
    });
  };

  const send = async () => {
    const message = input.trim();
    if (!message || busy) return;
    setInput("");
    setBusy(true);
    setEntries((e) => [...e, { role: "user", text: message }]);
    scrollBottom();
    try {
      for await (const ev of chatStream(message, history.current, selectedRef.current)) {
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
    <div className="chat" data-testid="chat">
      <div className="chat-log" ref={scroller} aria-live="polite">
        {entries.map((entry, i) => (
          <div key={i} className={`chat-entry role-${entry.role}`}>
            <span className="chat-role">{entry.role === "user" ? "you" : entry.role === "agent" ? "agent" : "…"}</span>
            <span className="chat-text">{entry.text}</span>
          </div>
        ))}
        {busy && <div className="chat-entry role-tool">…thinking</div>}
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
        <button type="button" onClick={() => void send()} disabled={busy}>Send</button>
      </div>
    </div>
  );
}
