import { useEffect, useState } from "react";
import { fetchSfxBoard, type SfxScene } from "../api";

interface SceneSlot {
  id: string;
  duration_s: number;
}

/**
 * The sound-effects bar: one block per scene, showing the baked scene audio's
 * waveform, the soundscape prompt that generated it, and the bell asset's
 * one-shot point. The split wav is the editable audio layer (reel.py sfx).
 */
export function SfxBar({ scenes, columns }: { scenes: SceneSlot[]; columns: string }) {
  const [board, setBoard] = useState<Record<string, SfxScene>>({});

  useEffect(() => {
    let live = true;
    fetchSfxBoard(72)
      .then((rows) => {
        if (live) setBoard(Object.fromEntries(rows.map((r) => [r.id, r])));
      })
      .catch(() => {});
    return () => {
      live = false;
    };
  }, [scenes.length]);

  return (
    <div className="lane lane-music lane-sfx" data-testid="lane-sfx"
      style={{ gridColumn: `1 / ${scenes.length + 1}`, gridTemplateColumns: columns }}>
      {scenes.map((s) => {
        const row = board[s.id];
        const title = row?.soundscape
          ? `${s.id} — ${row.soundscape}`
          : `${s.id} — no soundscape`;
        return (
          <div key={s.id} className={`sfx-block ${row?.split ? "" : "missing"}`}
            title={title} aria-label={`sound effects ${s.id}`}>
            {row?.peaks && <Waveform peaks={row.peaks} />}
            {row?.bell && (
              <span className="bell-mark"
                style={{ left: `${((row.bell_at ?? 0) / Math.max(s.duration_s, 0.01)) * 100}%` }}
                title={`bell: ${typeof row.bell === "string" ? row.bell : "(legacy synth)"} at +${row.bell_at ?? 0}s`}>
                🔔
              </span>
            )}
            <span className="sfx-name">{s.id}</span>
          </div>
        );
      })}
    </div>
  );
}

function Waveform({ peaks }: { peaks: number[] }) {
  const w = 100 / peaks.length;
  return (
    <svg className="waveform" viewBox="0 0 100 20" preserveAspectRatio="none"
      aria-hidden="true">
      {peaks.map((p, i) => (
        <rect key={i} x={i * w} y={10 - p * 10} width={w} height={Math.max(p * 20, 0.4)} />
      ))}
    </svg>
  );
}
