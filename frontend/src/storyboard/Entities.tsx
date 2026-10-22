import type { ProjectView } from "../types";

interface Props {
  project: ProjectView;
  /** the slug a narrative chip navigated to — scrolled to and highlighted */
  focus: string | null;
}

/**
 * The digested YAML of THIS project's reel.yaml — what the generator
 * actually consumes. No second parser: the read model carries the blocks.
 */
export function CharactersSection({ project, focus }: Props) {
  const slugs = Object.keys(project.characters);
  return (
    <div className="storyboard-scroll">
      {slugs.map((slug) => {
        const block = project.characters[slug];
        return (
          <Card key={slug} id={`characters-${slug}`} on={slug === focus}>
            <h4>{slug}</h4>
            {block.attributes &&
              <dl className="kv">
                {Object.entries(block.attributes).map(([k, v]) => (
                  <Row key={k} k={k} v={v} />
                ))}
              </dl>}
            {block.layers && Object.entries(block.layers).map(([name, layer]) => (
              <div key={name} className="layer">
                <h5>layer: {name}</h5>
                <dl className="kv">
                  {Object.entries(layer).map(([k, v]) => (
                    <Row key={k} k={k} v={v} />
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

export function LocationsSection({ project, focus }: Props) {
  const slugs = Object.keys(project.location_blocks);
  return (
    <div className="storyboard-scroll">
      {slugs.map((slug) => {
        const block = project.location_blocks[slug];
        return (
          <Card key={slug} id={`locations-${slug}`} on={slug === focus}>
            <h4>{slug}</h4>
            {block.pro && <p className="checkpoint-text">{block.pro}</p>}
            {block.con && <p className="con">− {block.con}</p>}
          </Card>
        );
      })}
      {slugs.length === 0 &&
        <p className="empty-hint">No locations in this scene's reel.yaml yet.</p>}
    </div>
  );
}

export function ScenesSection({ project }: Props) {
  return (
    <div className="storyboard-scroll">
      {project.scenes.map((s) => (
        <Card key={s.id} id={`scenes-${s.id}`} on={false}>
          <h4>{s.id}
            <span className="scene-meta">
              {s.frames} frames · {s.duration_s.toFixed(1)}s
              {s.stale && <b className="stale-badge"> stale</b>}
            </span>
          </h4>
          <p className="checkpoint-text">{s.description}</p>
        </Card>
      ))}
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

function Row({ k, v }: { k: string; v: string | string[] }) {
  const text = Array.isArray(v) ? v.join(", ") : v;
  return (
    <div className="kv-row">
      <dt>{k}</dt>
      <dd>{text}</dd>
    </div>
  );
}
