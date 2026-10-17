import type { MusicView, SceneView } from "../types";
import { audioRows, computeSlices, videoCell } from "./layout";

interface Props {
  scenes: SceneView[];
  music: MusicView[];
  totalS: number;
  artifactUrl: (sceneId: string, kind: string) => string;
  onSceneClick?: (sceneId: string) => void;
  onRenderScene?: (sceneId: string) => void;
  playheadPct: number | null;
}

function AnchorThumb({ label, kind, url }: { label: string; kind: string; url: string | null }) {
  return (
    <div className="anchor-thumb" title={`${label} (${kind})`}>
      {url ? (
        <img src={url} alt={label} loading="lazy" />
      ) : (
        <div className={`thumb-empty ${kind === "none" ? "empty" : ""}`}>
          {kind === "none" ? "" : kind === "prev_last" ? "⟵ prev" : "…"}
        </div>
      )}
      <span className="thumb-label">{label}</span>
    </div>
  );
}

export function Timeline({ scenes, music, totalS, artifactUrl, onSceneClick, onRenderScene, playheadPct }: Props) {
  const slices = computeSlices(scenes, totalS);
  return (
    <div className="timeline" data-testid="timeline">
      <div className="timeline-track" style={{ position: "relative" }}>
        {slices.map(({ id, startPct, widthPct, scene }) => {
          const cell = videoCell(scene);
          return (
            <div
              key={id}
              className={`slice ${scene.stale ? "stale" : ""}`}
              style={{ left: `${startPct}%`, width: `${widthPct}%` }}
              data-testid={`slice-${id}`}
              onClick={() => onSceneClick?.(id)}
            >
              <div className="slice-anchors">
                <AnchorThumb label="first" kind={scene.first.kind}
                  url={scene.first.kind === "none" ? null : artifactUrl(id, "thumb_first")} />
                <AnchorThumb label="last" kind={scene.last.kind}
                  url={scene.last.kind === "none" ? null : artifactUrl(id, "thumb_last")} />
              </div>
              <div className={`slice-video cell-${cell.kind}`}>
                {cell.kind === "missing" ? (
                  <span className="xxx" title="no render yet">XXX</span>
                ) : (
                  <video src={`${cell.url}#t=0.1`} muted preload="metadata" />
                )}
                {scene.stale && (
                  <button
                    className="mini-render"
                    title="re-render this scene"
                    onClick={(e) => { e.stopPropagation(); onRenderScene?.(id); }}
                  >
                    ↻ render
                  </button>
                )}
              </div>
              {audioRows(scene, music).map((row) => (
                <div key={row.label} className={`slice-audio ${row.url ? "has-audio" : "missing"}`}
                  title={row.url ? "clip audio" : undefined}>
                  {row.url ? (
                    <>
                      <span className="audio-tag" aria-hidden="true">♪</span>
                      <audio src={row.url} controls preload="none" aria-label={`${id} clip audio`} />
                    </>
                  ) : (
                    <span className="audio-missing" title="not rendered yet">XXX {row.label}</span>
                  )}
                </div>
              ))}
              <div className="slice-label">
                {id} · {scene.mode} · {scene.duration_s.toFixed(2)}s{scene.has_freeze ? " · freeze" : ""}
              </div>
            </div>
          );
        })}
        {playheadPct !== null && (
          <div className="playhead" style={{ left: `${playheadPct}%` }} data-testid="playhead" />
        )}
      </div>
    </div>
  );
}
