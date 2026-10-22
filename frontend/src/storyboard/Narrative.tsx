import { useState } from "react";
import type { Act, Checkpoint, NarrativeDoc } from "../api";

export type Section = "narrative" | "characters" | "locations" | "scenes";

interface Props {
  doc: NarrativeDoc;
  dirty: boolean;
  saving: boolean;
  /** mutate the draft — the parent owns the doc and the save */
  onChange: (doc: NarrativeDoc) => void;
  /** write a doc to storyboard.yaml (the pen's Save passes the draft) */
  onSave: (doc: NarrativeDoc) => void;
  onNavigate: (section: Section, slug: string) => void;
}

/**
 * The production narrative, top down: style, then every act with its
 * sync/music note and its checkpoint cards. Each checkpoint is its own
 * block with a pen icon top right — inline edit, or the agent edits it
 * through chat. `characters`/`locations` slug lists render as links into
 * the digested YAML sections.
 */
export function Narrative({ doc, dirty, saving, onChange, onSave, onNavigate }: Props) {
  const [editing, setEditing] = useState<string | null>(null); // "act:cp"
  const [draft, setDraft] = useState<{ title: string; text: string }>(
    { title: "", text: "" });

  const startEdit = (act: Act, i: number, j: number) => {
    const cp = act.checkpoints[j];
    setEditing(`${i}:${j}`);
    setDraft({ title: cp.title, text: cp.text });
  };

  const commit = () => {
    if (editing === null) return null;
    const [i, j] = editing.split(":").map(Number);
    const acts = doc.acts.map((a, ai) => ai !== i ? a : {
      ...a,
      checkpoints: a.checkpoints.map((cp, ci) => ci !== j ? cp : {
        ...cp, ...draft,
      }),
    });
    const next = { ...doc, acts };
    onChange(next);
    setEditing(null);
    return next;
  };

  return (
    <div className="storyboard-scroll">
      {doc.style && <p className="narrative-style">{doc.style}</p>}
      {doc.acts.map((act, i) => (
        <section key={i} className="narrative-act">
          <h3>{act.title}</h3>
          {act.music && <p className="narrative-music">🎵 {act.music}</p>}
          {act.checkpoints.map((cp, j) => {
            const key = `${i}:${j}`;
            return editing === key ? (
              <div key={key} className="checkpoint editing">
                <label>Title
                  <input value={draft.title}
                    onChange={(e) => setDraft({ ...draft, title: e.target.value })} />
                </label>
                <label>Text
                  <textarea rows={6} value={draft.text}
                    onChange={(e) => setDraft({ ...draft, text: e.target.value })} />
                </label>
                <div className="row-actions">
                  <button type="button"
                    onClick={() => { const next = commit(); if (next) onSave(next); }}
                    disabled={!draft.title || !draft.text}>Save</button>
                  <button type="button" onClick={() => setEditing(null)}>
                    Cancel</button>
                </div>
              </div>
            ) : (
              <CheckpointCard key={key} cp={cp} onEdit={() => startEdit(act, i, j)}
                onNavigate={onNavigate} />
            );
          })}
        </section>
      ))}
      {doc.acts.length === 0 &&
        <p className="empty-hint">No narrative yet — ask the agent to draft
          the story, or paste a prompt in chat.</p>}
      <div className="narrative-savebar">
        <button type="button" onClick={() => onSave(doc)} disabled={!dirty || saving}
          title="write the narrative to storyboard.yaml">
          {saving ? "Saving…" : dirty ? "Save narrative" : "Saved"}
        </button>
      </div>
    </div>
  );
}

function CheckpointCard({ cp, onEdit, onNavigate }: {
  cp: Checkpoint;
  onEdit: () => void;
  onNavigate: Props["onNavigate"];
}) {
  return (
    <article className="checkpoint">
      <button type="button" className="pen" title="edit this checkpoint"
        aria-label={`edit ${cp.title}`} onClick={onEdit}>✎</button>
      <h4>{cp.title}</h4>
      <p className="checkpoint-text">{cp.text}</p>
      {(cp.characters?.length || cp.locations?.length) &&
        <div className="ref-chips">
          {cp.characters?.map((slug) => (
            <button key={slug} type="button" className="chip"
              onClick={() => onNavigate("characters", slug)}
              title={`open character ${slug}`}>{slug}</button>
          ))}
          {cp.locations?.map((slug) => (
            <button key={slug} type="button" className="chip loc"
              onClick={() => onNavigate("locations", slug)}
              title={`open location ${slug}`}>{slug}</button>
          ))}
        </div>}
    </article>
  );
}
