import { useState } from "react";
import { saveBlock, API } from "../api";
import type { Anchor, CharacterBlock, ProjectView } from "../types";

interface Props {
  project: ProjectView;
  /** the slug a narrative chip navigated to — scrolled to and highlighted */
  focus: string | null;
  /** bump the app refresh after a pen save — the read model changed */
  onChanged: () => void;
}

/** keys of a character block that are NOT prompt values */
const NON_PROMPT = new Set(["ref", "attributes", "layers", "variants",
  "seeds"]);

/**
 * The digested YAML of THIS project's reel.yaml — what the generator
 * actually consumes. No second parser: the read model carries the blocks.
 * Every prompt value has a pen for inline editing; the edit replaces the
 * one block through PUT /api/block — the server owns the validated dump.
 */
export function CharactersSection({ project, focus, onChanged }: Props) {
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);

  const close = () => setEditing(null);

  const save = async (slug: string, path: (string | number)[],
                      block: CharacterBlock) => {
    const next = structuredClone(block);
    let node = next as Record<string, unknown>;
    for (let i = 0; i < path.length - 1; i++) {
      node = node[path[i] as string] as Record<string, unknown>;
    }
    node[path[path.length - 1] as string] = draft;
    try {
      await saveBlock("characters", slug, next);
      setEditing(null);
      setError(null);
      onChanged();
    } catch (e) {
      setError(String(e));
    }
  };

  const slugs = Object.keys(project.characters);
  return (
    <div className="storyboard-scroll">
      {error && <div className="app-error" onClick={() => setError(null)}>
        {error} (click to dismiss)</div>}
      {slugs.map((slug) => {
        const block = project.characters[slug];
        return (
          <Card key={slug} id={`characters-${slug}`} on={slug === focus}>
            <h4>{slug}</h4>
            {Object.entries(block)
              .filter(([k, v]) => !NON_PROMPT.has(k) && typeof v === "string")
              .map(([k, v]) => (
                <ValueRow key={k} k={k} v={v as string}
                  pen={editing === `${slug}:${k}`}
                  onPen={() => { setEditing(`${slug}:${k}`);
                    setDraft(v as string); }}
                  onClose={close}
                  onDraft={setDraft}
                  onSave={() => save(slug, [k], block)} />
              ))}
            {block.attributes &&
              <dl className="kv">
                {Object.entries(block.attributes).map(([k, v]) => (
                  <ValueRow key={k} k={k} v={v}
                    pen={editing === `${slug}:a:${k}`}
                    onPen={() => { setEditing(`${slug}:a:${k}`);
                      setDraft(String(v)); }}
                    onClose={close}
                    onDraft={setDraft}
                    onSave={() => save(slug, ["attributes", k], block)} />
                ))}
              </dl>}
            {block.layers && Object.entries(block.layers).map(([name, layer]) => (
              <div key={name} className="layer">
                <h5>layer: {name}</h5>
                <dl className="kv">
                  {Object.entries(layer).map(([k, v]) => (
                    <ValueRow key={k} k={k} v={v}
                      pen={editing === `${slug}:l:${name}:${k}`}
                      onPen={() => { setEditing(`${slug}:l:${name}:${k}`);
                        setDraft(String(v)); }}
                      onClose={close}
                      onDraft={setDraft}
                      onSave={() => save(slug, ["layers", name, k], block)} />
                  ))}
                </dl>
              </div>
            ))}
            {block.variants && <h5>variants ({block.variants.length})</h5>}
            {block.variants?.map((v, i) => (
              <p key={i} className="variant">
                <b>{String((v as { slug?: string }).slug ?? i)}</b>
                {" — "}{String((v as { pose?: string }).pose ?? "")}
              </p>
            ))}
          </Card>
        );
      })}
      {slugs.length === 0 &&
        <p className="empty-hint">No characters in this scene's reel.yaml
          yet — draft them from the narrative in chat.</p>}
    </div>
  );
}

export function LocationsSection({ project, focus, onChanged }: Props) {
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);

  const close = () => setEditing(null);

  const save = async (slug: string, key: "pro" | "con") => {
    const next = structuredClone(project.location_blocks[slug]);
    next[key] = draft;
    try {
      await saveBlock("locations", slug, next);
      setEditing(null);
      setError(null);
      onChanged();
    } catch (e) {
      setError(String(e));
    }
  };

  const slugs = Object.keys(project.location_blocks);
  return (
    <div className="storyboard-scroll">
      {error && <div className="app-error" onClick={() => setError(null)}>
        {error} (click to dismiss)</div>}
      {slugs.map((slug) => {
        const block = project.location_blocks[slug];
        return (
          <Card key={slug} id={`locations-${slug}`} on={slug === focus}>
            <h4>{slug}</h4>
            {block.pro && <ValueRow k="pro" v={block.pro}
              pen={editing === `${slug}:pro`}
              onPen={() => { setEditing(`${slug}:pro`); setDraft(block.pro!); }}
              onClose={close}
              onDraft={setDraft}
              onSave={() => save(slug, "pro")} />}
            {block.con && <p className="con">− {block.con}</p>}
          </Card>
        );
      })}
      {slugs.length === 0 &&
        <p className="empty-hint">No locations in this scene's reel.yaml yet.</p>}
    </div>
  );
}

interface ScenesProps extends Props {
  /** the pen on a scene card: edit this beat's action text — the shot in
   * storyboard.yaml that owns the language of the scene's prompt */
  onEditBeat: (beat: string) => void;
}

export function ScenesSection({ project, focus, onEditBeat }: ScenesProps) {
  return (
    <div className="storyboard-scroll">
      {project.scenes.map((s) => (
        <Card key={s.id} id={`scenes-${s.id}`} on={focus === s.id}>
          <h4>{s.id}
            <span className="scene-meta">
              {s.frames} frames · {s.duration_s.toFixed(1)}s
              {s.stale && <b className="stale-badge"> stale</b>}
            </span>
          </h4>
          <div className="anchor-stills">
            <AnchorThumb label="first" anchor={s.first} />
            <AnchorThumb label="last" anchor={s.last} />
          </div>
          {s.beat &&
            <button type="button" className="pen prompt-pen"
              title="edit this scene's action text — the beat in
                storyboard.yaml that owns the language of the prompt below"
              onClick={() => onEditBeat(s.beat!)}>✎ edit action text</button>}
          <p className="checkpoint-text prompt">
            {s.prompt || s.description
              || (s.beat ? "no composed prompt — reel.py cannot collapse yet"
                         : "no prompt wired for this scene")}</p>
        </Card>
      ))}
    </div>
  );
}

function AnchorThumb({ label, anchor }: { label: string; anchor: Anchor }) {
  if (!anchor.path) {
    return <span className="anchor-thumb empty">{label}: {anchor.kind}</span>;
  }
  const src = `${API}/asset/file?path=${encodeURIComponent(anchor.path)}`;
  return (
    <figure className="anchor-thumb">
      <img src={src} alt={`${label} anchor still`} loading="lazy" />
      <figcaption>{label}</figcaption>
    </figure>
  );
}

/** one editable prompt value: the value, a pen, and — while its pen is
 * active — an inline textarea replacing the value */
function ValueRow({ k, v, pen, onPen, onClose, onDraft, onSave }: {
  k: string;
  v: string | string[];
  pen: boolean;
  onPen: () => void;
  onClose: () => void;
  onDraft: (d: string) => void;
  onSave: () => void;
}) {
  if (pen) {
    return (
      <div className="kv-row editing">
        <dt>{k}</dt>
        <dd>
          <textarea rows={4} value={v as string}
            onChange={(e) => onDraft(e.target.value)} autoFocus />
          <div className="row-actions">
            <button type="button" onClick={onSave}>Save</button>
            <button type="button" onClick={onClose}>Cancel</button>
          </div>
        </dd>
      </div>
    );
  }
  const text = Array.isArray(v) ? v.join(", ") : v;
  return (
    <div className="kv-row">
      <dt>{k}</dt>
      <dd>{text}
        <button type="button" className="pen" title={`edit ${k}`}
          onClick={onPen}>✎</button>
      </dd>
    </div>
  );
}

function Card({ id, on, children }: {
  id: string;
  on: boolean;
  children: React.ReactNode;
}) {
  return (
    <article id={id} className={on ? "entity-card focused" : "entity-card"}>
      {children}
    </article>
  );
}
