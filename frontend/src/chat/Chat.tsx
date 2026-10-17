import { useRef, useState } from "react";
import { chatStream } from "../api";
import type { ChatEvent } from "../types";

interface Entry {
  role: "user" | "agent" | "tool";
  text: string;
}

interface Props {
  onProjectChanged?: () => void;
}

export function Chat({ onProjectChanged }: Props) {
  const [entries, setEntries] = useState<Entry[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const history = useRef<{ role: string; content: string }[]>([]);
  const scroller = useRef<HTMLDivElement | null>(null);

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
      for await (const ev of chatStream(message, history.current)) {
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
        : ev.name === "render_scenes"
          ? `rendering ${(args?.scene_ids as string[] | undefined)?.join(", ") || "stale scenes"}`
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
      <div className="chat-log" ref={scroller}>
        {entries.length === 0 && (
          <div className="chat-hint">
            Ask the agent to edit this reel — e.g. "make scene 2 shorter" or
            "fix the junction between the bowl drop and the draw".
          </div>
        )}
        {entries.map((entry, i) => (
          <div key={i} className={`chat-entry role-${entry.role}`}>{entry.text}</div>
        ))}
        {busy && <div className="chat-entry role-tool">…thinking</div>}
      </div>
      <div className="chat-input">
        <input
          value={input}
          placeholder={busy ? "agent is working…" : "tell the agent what to change"}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") void send(); }}
          disabled={busy}
        />
        <button onClick={() => void send()} disabled={busy}>Send</button>
      </div>
    </div>
  );
}
