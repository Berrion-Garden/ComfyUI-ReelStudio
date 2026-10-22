import { useState } from "react";
import type { Checkpoint, NarrativeDoc } from "../api";

export type Section = "narrative" | "characters" | "locations" | "scenes";

interface Props {
  doc: NarrativeDoc;
  dirty: boolean;
  saving: boolean;
  /** mutate the draft — the parent owns the doc and the save */
  onChange: (doc: NarrativeDoc) => void;
  /** write a doc to storyboard.yaml (a pen's Save passes the draft) */
  onSave: (doc: NarrativeDoc) => void;
  onNavigate: (section: Section, slug: string) => void;
}

/**
 * The production narrative, top down: style, then every act (with its
 * sync/music note) of scene checkpoints, each holding its shot prompts —
 * the original script's exact shape. Every scene card and shot has a pen
 * icon top right for inline editing; the agent edits through chat
 * equally. `characters`/`locations` slugs render as links into the
 * digested YAML sections.
 */
export function Narrative({ doc, dirty, saving, onChange, onSave, onNavigate }: Props) {
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState<{ title: string; text: string }>(
    { title: "", text: "" });

  const startEdit = (key: string, title: string, text: string) => {
    setEditing(key);
    setDraft({ title, text });
  };

  /** apply the draft to the one node `key` addresses (a scene or a shot) */
  const commit = () => {
    if (editing === null) return null;
    const [ai, ci, si] = editing.split(":").map(Number);
    const acts = doc.acts.map((act, i) => {
      if (i !== ai) return act;
      const checkpoints = act.checkpoints.map((cp, j) => {
        if (j !== ci) return cp;
        if (Number.isNaN(si)) return { ...cp, title: draft.title };
        return {
          ...cp,
          shots: cp.shots.map((shot, k) => k !== si ? shot
            : { ...shot, ...draft }),
        };
      });
      return { ...act, checkpoints };
    });
    const next = { ...doc, acts };
    onChange(next);
    setEditing(null);
    return next;
  };

  const saveOrCommit = () => {
    const next = commit();
    if (next) onSave(next);
  };

  return (
    <div className="storyboard-scroll">
      {doc.style && <p className="narrative-style">{doc.style}</p>}
      {doc.acts.map((act, i) => (
        <section key={i} className="narrative-act">
          <h3>{act.title}</h3>
          {act.music && <p className="narrative-music">🎵 {act.music}</p>}
          {act.checkpoints.map((cp, j) => (
            <SceneCard key={j} cp={cp} editing={editing} draft={draft}
              setDraft={setDraft} startEdit={startEdit} cancelEdit={() => setEditing(null)}
              commit={commit} saveOrCommit={saveOrCommit}
              sceneKey={`${i}:${j}`} onNavigate={onNavigate} />
          ))}
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

interface SceneProps {
  cp: Checkpoint;
  editing: string | null;
  draft: { title: string; text: string };
  setDraft: (d: { title: string; text: string }) => void;
  startEdit: (key: string, title: string, text: string) => void;
  cancelEdit: () => void;
  commit: () => void;
  saveOrCommit: () => void;
  sceneKey: string;
  onNavigate: Props["onNavigate"];
}

function SceneCard({ cp, editing, draft, setDraft,
                     startEdit, cancelEdit, commit, saveOrCommit,
                     sceneKey, onNavigate }: SceneProps) {
  return (
    <article className="checkpoint scene">
      <button type="button" className="pen"
        title="edit this scene's title" aria-label={`edit scene ${cp.title}`}
        onClick={() => startEdit(sceneKey, cp.title, "")}>✎</button>
      <h4><b className="beat-id" title="the beat id reel.yaml wires to">{cp.id}</b>{cp.title}</h4>
      {(cp.characters.length > 0 || cp.locations.length > 0) &&
        <div className="ref-chips">
          {cp.characters.map((slug) => (
            <button key={slug} type="button" className="chip"
              onClick={() => onNavigate("characters", slug)}
              title={`open character ${slug}`}>{slug}</button>
          ))}
          {cp.locations.map((slug) => (
            <button key={slug} type="button" className="chip loc"
              onClick={() => onNavigate("locations", slug)}
              title={`open location ${slug}`}>{slug}</button>
          ))}
        </div>}
      {cp.shots.map((shot, k) => {
        const key = `${sceneKey}:${k}`;
        return editing === key ? (
          <div key={key} className="shot editing">
            <label>Title
              <input value={draft.title}
                onChange={(e) => setDraft({ ...draft, title: e.target.value })} />
            </label>
            <label>Text
              <textarea rows={6} value={draft.text}
                onChange={(e) => setDraft({ ...draft, text: e.target.value })} />
            </label>
            <div className="row-actions">
              <button type="button" onClick={saveOrCommit}
                disabled={!draft.text}>Save</button>
              <button type="button" onClick={cancelEdit}>Cancel</button>
            </div>
          </div>
        ) : (
          <div key={key} className="shot">
            <button type="button" className="pen"
              title="edit this shot" aria-label={`edit ${shot.title || cp.title}`}
              onClick={() => startEdit(key, shot.title, shot.text)}>✎</button>
            {shot.title && <h5>{shot.title}</h5>}
            <p className="checkpoint-text">{shot.text}</p>
          </div>
        );
      })}
      {editing === sceneKey && (
        <div className="shot editing">
          <label>Title
            <input value={draft.title}
              onChange={(e) => setDraft({ ...draft, title: e.target.value })} />
          </label>
          <div className="row-actions">
            <button type="button" onClick={commit}
              disabled={!draft.title}>Save</button>
            <button type="button" onClick={cancelEdit}>Cancel</button>
          </div>
        </div>
      )}
    </article>
  );
}
