import type { SceneView } from "../types";

interface Props {
  scenes: SceneView[];
  artifactUrl: (sceneId: string, kind: string) => string;
}

/**
 * The reel's images — every scene's resolved first/last anchor still — as a
 * grid, so the player section can visualize them without the video chain.
 */
export function Stills({ scenes, artifactUrl }: Props) {
  const cells: { key: string; url: string; label: string }[] = [];
  for (const s of scenes) {
    if (s.first.kind !== "none") {
      cells.push({
        key: `${s.id}-first`, url: artifactUrl(s.id, "thumb_first"),
        label: `${s.id} · first`,
      });
    }
    if (s.last.kind !== "none") {
      cells.push({
        key: `${s.id}-last`, url: artifactUrl(s.id, "thumb_last"),
        label: `${s.id} · last`,
      });
    }
  }

  return (
    <div className="stills" aria-label="scene stills">
      {cells.map((c) => (
        <a key={c.key} className="still" href={c.url} target="_blank" rel="noreferrer"
          title={`${c.label} — click to view full size`}>
          <img src={c.url} alt={c.label} loading="lazy" />
          <span>{c.label}</span>
        </a>
      ))}
      {cells.length === 0 && (
        <div className="stills-empty">no stills yet — render or generate anchors first</div>
      )}
    </div>
  );
}
