import { useEffect, useMemo, useState } from "react";
import { fetchAssets, type AssetItem, type AssetsData } from "../api";
import type { SelectedAsset } from "../player/Player";

interface Props {
  selected: SelectedAsset | null;
  onSelect: (asset: SelectedAsset | null) => void;
}

/** Groups characters by their `char:<slug>` label into per-pool subsections. */
function characterPools(items: AssetItem[]): { pool: string; assets: AssetItem[] }[] {
  const pools = new Map<string, AssetItem[]>();
  for (const a of items) {
    const label = a.labels.find((l) => l.startsWith("char:")) ?? "char:unsorted";
    if (!pools.has(label)) pools.set(label, []);
    pools.get(label)!.push(a);
  }
  return [...pools.entries()].map(([pool, assets]) => ({ pool: pool.slice(5), assets }));
}

export function AssetsPane({ selected, onSelect }: Props) {
  const [data, setData] = useState<AssetsData | null>(null);

  useEffect(() => {
    void fetchAssets().then(setData).catch(() => setData({ groups: {
      characters: [], scenes: [], custom: [], themes: [], audio: [],
    }}));
  }, []);

  const sections = useMemo(() => {
    if (!data) return [];
    const g = data.groups;
    const out: { title: string; open: boolean; assets: AssetItem[] }[] = [
      { title: "Characters", open: true, assets: g.characters },
      { title: "Scenes", open: true, assets: g.scenes },
      { title: "Custom", open: false, assets: g.custom },
      { title: "LORA / Theme", open: false, assets: g.themes },
      { title: "Audio", open: false, assets: g.audio },
    ];
    return out;
  }, [data]);

  // flat order for arrow-key navigation, top to bottom
  const flat = useMemo(() => sections.flatMap((s) => s.assets), [sections]);

  const move = (dir: 1 | -1) => {
    if (flat.length === 0) return;
    const idx = selected ? flat.findIndex((a) => a.url === selected.url) : -1;
    const next = flat[Math.min(Math.max(idx + dir, 0), flat.length - 1)];
    if (next) onSelect({ url: next.url, name: next.slug });
  };

  const card = (a: AssetItem) => {
    const isImage = !a.url.endsWith(".mp3") && !a.url.endsWith(".wav");
    const isSel = selected?.url === a.url;
    return (
      <button
        key={a.path}
        type="button"
        className={`asset-card ${isSel ? "selected" : ""}`}
        onClick={() => onSelect(isSel ? null : { url: a.url, name: a.slug })}
        title={`${a.slug}\n${a.labels.join(" · ")}${a.used_by.length ? `\nused by: ${a.used_by.join(", ")}` : ""}`}
        data-testid={`asset-${a.group}-${a.slug}`}
      >
        {isImage ? (
          <img src={a.url} alt={a.slug} loading="lazy" />
        ) : (
          <span className="asset-audio">♪</span>
        )}
        <span className="name">{a.slug}</span>
        {a.used_by.length > 0 && (
          <span className="usedby">in {a.used_by.length} scene{a.used_by.length > 1 ? "s" : ""}</span>
        )}
      </button>
    );
  };

  return (
    <div className="assets-pane" data-testid="assets-pane"
      tabIndex={0}
      aria-label="asset library"
      onKeyDown={(e) => {
        if (e.key === "ArrowDown") { e.preventDefault(); move(1); }
        if (e.key === "ArrowUp") { e.preventDefault(); move(-1); }
      }}>
      <div className="assets-header">Assets</div>
      {data === null && <div className="assets-loading">loading assets…</div>}
      {sections.map((s) => (
        <details key={s.title} className="asset-section" open={s.open}>
          <summary>{s.title} <span className="count">{s.assets.length}</span></summary>
          {s.title === "Characters" && s.assets.length > 0 ? (
            characterPools(s.assets).map(({ pool, assets }) => (
              <div key={pool} className="asset-pool">
                <div className="pool-name">{pool}</div>
                <div className="asset-grid">{assets.map(card)}</div>
              </div>
            ))
          ) : (
            <div className="asset-grid">{s.assets.map(card)}</div>
          )}
        </details>
      ))}
    </div>
  );
}
