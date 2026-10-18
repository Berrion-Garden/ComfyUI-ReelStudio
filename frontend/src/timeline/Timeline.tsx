import type { MusicView, OverlayView, SceneView } from "../types";
import { spanCols, videoCell } from "./layout";
import { AudioLane } from "./AudioLane";
import { SfxBar } from "./SfxBar";

interface Props {
  scenes: SceneView[];
  music: MusicView[];
  overlays?: OverlayView[];
  totalS: number;
  artifactUrl: (sceneId: string, kind: string) => string;
  onSceneClick?: (sceneId: string) => void;
  onRenderScene?: (sceneId: string) => void;
  onAdoptScene?: (sceneId: string) => void;
  onTrackChange?: (index: number, fades: [number, number][]) => void;
  sfxRows?: import("../api").SfxScene[];
  onPlaceSfx?: (sceneId: string, asset: string, at: number) => void;
  onRemoveSfx?: (sceneId: string, index: number) => void;
  playheadPct: number | null;
  onSeek?: (pct: number) => void;
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

export function Timeline({ scenes, music, overlays = [], totalS, artifactUrl, onSceneClick, onRenderScene, onAdoptScene, onTrackChange, sfxRows, onPlaceSfx, onRemoveSfx, playheadPct, onSeek }: Props) {
  const columns = scenes.map((s) => `${Math.max(s.duration_s, 0.4)}fr`).join(" ");
  const ticks: number[] = [];
  for (let t = 0; t < totalS - 0.01; t += 5) ticks.push(t);

  const scrub = (e: React.PointerEvent) => {
    if (!onSeek) return;
    const rect = e.currentTarget.getBoundingClientRect();
    onSeek(Math.min(Math.max((e.clientX - rect.left) / rect.width, 0), 1) * 100);
  };

  // the real-file overlays are the tracks the mix uses; the generated
  // segments only fill the lanes when there are no overlays at all
  const musicLanes: Array<{ name: string; startS: number; durS: number; present: boolean; url: string | null; kind: string }> =
    overlays.length > 0
      ? overlays.map((o) => ({ name: o.name, startS: o.start_s, durS: o.duration_s, present: o.present, url: o.url, kind: "overlay" }))
      : music.map((m) => ({ name: m.name, startS: m.start_s, durS: m.duration_s, present: m.present, url: m.url, kind: "generated" }));

  return (
    <div className="timeline" data-testid="timeline">
      <div
        className="timeline-track"
        style={{ gridTemplateColumns: columns }}
        onPointerDown={(e) => {
          try { (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId); } catch { /* jsdom */ }
          scrub(e);
        }}
        onPointerMove={(e) => { if (e.buttons & 1) scrub(e); }}
      >
        {ticks.length > 1 && (
          <div className="lane lane-ruler" style={{ gridColumn: `1 / ${scenes.length + 1}` }}>
            {ticks.map((t) => (
              <span key={t} className="ruler-tick" style={{ left: `${(t / totalS) * 100}%` }}>
                {t}s
              </span>
            ))}
          </div>
        )}

        {scenes.map((s, i) => (
          <div key={`${s.id}-anchors`} className="lane lane-anchors" style={{ gridColumn: `${i + 1}` }}>
            <AnchorThumb label="first" kind={s.first.kind}
              url={s.first.kind === "none" ? null : artifactUrl(s.id, "thumb_first")} />
            <AnchorThumb label="last" kind={s.last.kind}
              url={s.last.kind === "none" ? null : artifactUrl(s.id, "thumb_last")} />
          </div>
        ))}

        {scenes.map((s, i) => {
          const cell = videoCell(s);
          return (
            <div key={`${s.id}-video`} data-testid={`slice-${s.id}`}
              className={`lane lane-video ${s.stale ? "stale" : ""}`}
              style={{ gridColumn: `${i + 1}` }}
              onClick={() => onSceneClick?.(s.id)}>
              {cell.kind === "missing" ? (
                <span className="xxx" title="no render yet">XXX</span>
              ) : (
                <video src={`${cell.url}#t=0.1`} muted preload="metadata" />
              )}
              {s.has_bell && <span className="cell-flag" title="synth bell in post">🔔</span>}
              {s.stale && (
                <button
                  className="mini-render"
                  title="re-render this scene"
                  onClick={(e) => { e.stopPropagation(); onRenderScene?.(s.id); }}
                >
                  ↻ render
                </button>
              )}
              {s.adoptable && (
                <button
                  className="mini-render adopt"
                  title="declare this render matches the current config — adopt it without re-rendering"
                  onClick={(e) => { e.stopPropagation(); onAdoptScene?.(s.id); }}
                >
                  ✓ adopt
                </button>
              )}
              <span className="cell-label">{s.id} · {s.duration_s.toFixed(2)}s{s.has_freeze ? " · freeze" : ""}</span>
            </div>
          );
        })}

        {scenes.some((s) => s.has_sfx) && (
          <SfxBar
            scenes={scenes.map((s) => ({ id: s.id, duration_s: s.duration_s }))}
            rows={sfxRows ?? []}
            onPlace={onPlaceSfx}
            onRemove={onRemoveSfx}
            columns={columns} />
        )}

        {musicLanes.map((m) => {
          const span = spanCols(scenes, m.startS, m.durS);
          if (m.kind === "overlay") {
            const ov = overlays.find((o) => o.name === m.name)!;
            return (
              <AudioLane key={m.name} overlay={ov} totalS={totalS}
                columns={columns} span={span} sceneCount={scenes.length}
                onChange={onTrackChange} />
            );
          }
          return (
            <div key={m.name} data-testid={`lane-${m.name}`} className="lane lane-music"
              style={{ gridColumn: `1 / ${scenes.length + 1}`, gridTemplateColumns: columns }}>
              <div className={`music-block ${m.present ? "" : "missing"}`}
                style={{ gridColumn: `${span.start} / ${span.end}` }}>
                {m.present ? (
                  <audio src={`${m.url}#t=0`} controls preload="none"
                    aria-label={`music ${m.name}`} title={`${m.name} — spans scenes ${span.start}–${span.end - 1}`} />
                ) : (
                  <span className="audio-missing" title="not rendered yet">XXX {m.name}</span>
                )}
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
