import { useEffect, useRef, useState } from "react";
import type { OverlayView } from "../types";
import { fetchAudioPeaks } from "../api";

interface Props {
  overlay: OverlayView;
  totalS: number;
  columns: string;
  span: { start: number; end: number };
  sceneCount: number;
  /** commit a new fades envelope (volume anchors) for this track */
  onChange?: (index: number, fades: [number, number][]) => void;
}

/**
 * The audio-graph view of one real audio track: waveform (peaks from the
 * server), draggable volume anchors (the yaml fades keyframes), add by
 * click, delete by double-click. Commits on drag end — reel.yaml stays the
 * single source of truth.
 */
export function AudioLane({ overlay, columns, span, sceneCount, onChange }: Props) {
  const [peaks, setPeaks] = useState<number[] | null>(null);
  const [fades, setFades] = useState<[number, number][]>(overlay.fades);
  const dragging = useRef<number | null>(null);
  const block = useRef<HTMLDivElement | null>(null);

  useEffect(() => setFades(overlay.fades), [overlay.fades]);

  useEffect(() => {
    let alive = true;
    if (overlay.url) {
      fetchAudioPeaks(overlay.index).then(
        (p) => { if (alive) setPeaks(p); },
        () => { /* no waveform on failure — the lane still works */ },
      );
    }
    return () => { alive = false; };
  }, [overlay.index, overlay.url]);

  const pointFromEvent = (e: { clientX: number; clientY: number }): [number, number] | null => {
    const rect = block.current?.getBoundingClientRect();
    if (!rect) return null;
    const frac = Math.min(1, Math.max(0, (e.clientX - rect.left) / rect.width));
    const vol = Math.min(1, Math.max(0, 1 - (e.clientY - rect.top) / rect.height));
    const t = overlay.start_s + frac * overlay.duration_s;
    return [Number(t.toFixed(2)), Number(vol.toFixed(2))];
  };

  useEffect(() => {
    if (!onChange) return;
    const move = (e: PointerEvent) => {
      if (dragging.current === null) return;
      const point = pointFromEvent(e);
      if (!point) return;
      setFades((cur) => cur.map(([t], i) =>
        i === dragging.current ? point : [t, cur[i][1]] as [number, number]));
    };
    const up = () => {
      if (dragging.current === null) return;
      dragging.current = null;
      setFades((cur) => {
        const sorted = [...cur].sort((a, b) => a[0] - b[0]);
        onChange(overlay.index, sorted);
        return sorted;
      });
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
    return () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [onChange, overlay.index, overlay.start_s, overlay.duration_s]);

  const addAnchor = (e: React.MouseEvent) => {
    if (!onChange) return;
    const point = pointFromEvent(e);
    if (!point) return;
    const next = [...fades, point].sort((a, b) => a[0] - b[0]);
    setFades(next);
    onChange(overlay.index, next);
  };

  const removeAnchor = (i: number) => {
    if (!onChange) return;
    const next = fades.filter((_, k) => k !== i);
    setFades(next);
    onChange(overlay.index, next);
  };

  return (
    <div className="lane lane-music lane-audio" data-testid={`lane-${overlay.name}`}
      style={{ gridColumn: `1 / ${sceneCount + 1}`, gridTemplateColumns: columns }}>
      <div
        className={`music-block audio-graph ${overlay.present ? "" : "missing"}`}
        style={{ gridColumn: `${span.start} / ${span.end}` }}
        ref={block}
        onClick={(e) => {
          if ((e.target as HTMLElement).classList.contains("anchor")) return;
          addAnchor(e);
        }}
      >
        {overlay.present ? (
          <audio src={`${overlay.url}#t=${overlay.seek}`} controls preload="none"
            aria-label={`music ${overlay.name}`}
            title={`${overlay.name} — starts at source ${Math.round(overlay.seek)}s, as the yaml says`} />
        ) : (
          <span className="audio-missing" title="file missing">XXX {overlay.name}</span>
        )}
        {peaks && (
          <svg className="waveform" viewBox="0 0 100 10" preserveAspectRatio="none"
            aria-hidden="true">
            {peaks.map((p, i) => (
              <rect key={i} x={i / peaks.length * 100} width={100 / peaks.length}
                y={5 - p * 4.5} height={Math.max(0.15, p * 9)} />
            ))}
          </svg>
        )}
        {fades.map(([t, v], i) => (
          <span key={`${t}-${i}`} className="anchor" data-testid={`anchor-${i}`}
            title={`${t.toFixed(1)}s @ ${Math.round(v * 100)}% — drag to shape, double-click to remove`}
            style={{ left: `${Math.min(100, Math.max(0, (t - overlay.start_s) / overlay.duration_s)) * 100}%`, bottom: `${v * 100}%` }}
            onPointerDown={(e) => {
              e.stopPropagation();
              dragging.current = i;
            }}
            onDoubleClick={(e) => { e.stopPropagation(); removeAnchor(i); }}
          />
        ))}
      </div>
    </div>
  );
}
