import { useEffect, useState } from "react";
import { fetchAssets, type SfxScene } from "../api";

interface SceneSlot {
  id: string;
  duration_s: number;
}

interface Props {
  scenes: SceneSlot[];
  rows: SfxScene[];
  columns: string;
  onPlace?: (sceneId: string, asset: string, at: number) => void;
  onRemove?: (sceneId: string, index: number) => void;
}

/**
 * The sound-effects board lane: one block per scene showing the baked scene
 * audio's waveform, the soundscape prompt that generated it, the bell asset's
 * one-shot point, and the placed sfx assets. Click a block to place an asset
 * from the library at that moment (written to reel.yaml, played by the mix);
 * double-click a placement to remove it.
 */
export function SfxBar({ scenes, rows, columns, onPlace, onRemove }: Props) {
  const [library, setLibrary] = useState<string[]>([]);
  const [picking, setPicking] = useState<{ id: string; at: number } | null>(null);
  const [choice, setChoice] = useState<string>("");

  useEffect(() => {
    let alive = true;
    fetchAssets().then((data) => {
      if (alive) {
        setLibrary(data.groups.sfx.map((a) => a.slug));
      }
    }).catch(() => { /* the picker just stays empty */ });
    return () => { alive = false; };
  }, []);

  const board = Object.fromEntries(rows.map((r) => [r.id, r]));

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
            title={title} aria-label={`sound effects ${s.id}`}
            onClick={(e) => {
              if (!onPlace || (e.target as HTMLElement).closest(".sfx-marker, .sfx-picker")) return;
              const rect = e.currentTarget.getBoundingClientRect();
              const frac = Math.min(1, Math.max(0, (e.clientX - rect.left) / rect.width));
              setPicking({ id: s.id, at: Number((frac * s.duration_s).toFixed(2)) });
              setChoice(library[0] ?? "");
            }}>
            {row?.peaks && <Waveform peaks={row.peaks} />}
            {row?.bell && (
              <span className="bell-mark sfx-marker"
                style={{ left: `${((row.bell_at ?? 0) / Math.max(s.duration_s, 0.01)) * 100}%` }}
                title={`bell: ${typeof row.bell === "string" ? row.bell : "(in yaml)"} at +${row.bell_at ?? 0}s`}>
                🔔
              </span>
            )}
            {(row?.assets ?? []).map((a, i) => (
              <span key={`${a.asset}-${i}`} className="sfx-marker"
                data-testid={`sfx-${s.id}-${i}`}
                style={{ left: `${(a.at / Math.max(s.duration_s, 0.01)) * 100}%` }}
                title={`${a.asset} at +${a.at}s (gain ${Math.round(a.gain * 100)}%) — double-click to remove`}
                onDoubleClick={(e) => {
                  e.stopPropagation();
                  onRemove?.(s.id, i);
                }}>
                ♪
              </span>
            ))}
            <span className="sfx-name">{s.id}</span>
            {picking?.id === s.id && (
              <span className="sfx-picker" onClick={(e) => e.stopPropagation()}>
                <select value={choice} aria-label={`asset for ${s.id}`}
                  onChange={(e) => setChoice(e.target.value)}>
                  {library.length === 0 && <option value="">no sfx assets in the library</option>}
                  {library.map((slug) => <option key={slug} value={slug}>{slug}</option>)}
                </select>
                <span className="sfx-picker-at">+{picking.at.toFixed(2)}s</span>
                <button disabled={!choice} onClick={() => {
                  onPlace?.(picking.id, choice, picking.at);
                  setPicking(null);
                }}>place</button>
                <button onClick={() => setPicking(null)}>✕</button>
              </span>
            )}
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
