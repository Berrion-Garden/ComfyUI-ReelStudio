import { useEffect, useMemo, useState } from "react";
import { fetchAssets, setAssetLabels, type AssetItem, type AssetsData } from "../api";

interface Props {
  assets: AssetsData | null;
  selected: AssetItem | null;
  onSelect: (a: AssetItem | null) => void;
  /** refetch the library after a label edit (labels are derived server-side) */
  onChanged: () => void;
}

const GRID_GROUPS: { title: string; group: AssetItem["group"] }[] = [
  { title: "Scenes", group: "scenes" },
  { title: "Characters", group: "characters" },
  { title: "Backgrounds", group: "backgrounds" },
  { title: "Custom", group: "custom" },
  { title: "Audio", group: "audio" },
  { title: "Sound FX", group: "sfx" },
];

const IMAGE_EXTS = [".png", ".jpg", ".jpeg", ".webp"];

function isImage(a: AssetItem): boolean {
  return IMAGE_EXTS.some((e) => a.url.toLowerCase().endsWith(e));
}

/**
 * The stage's asset browser: the selected asset large and interactive on the
 * left (image full-frame, audio a player), the picker grid on the right.
 * The inspector also edits the asset's declared labels — typed free-form
 * (`char:<slug>`, `scene:<slug>`, `cond:<x>`, anything) — the one place the
 * operator both sees and annotates an asset.
 */
export function AssetBrowser({ assets, selected, onSelect, onChanged }: Props) {
  const groups = useMemo(() => {
    if (!assets) return [];
    return GRID_GROUPS
      .map(({ title, group }) => ({ title, assets: assets.groups[group] ?? [] }))
      .filter((s) => s.assets.length > 0);
  }, [assets]);

  return (
    <div className="asset-browser">
      <div className="asset-inspector" data-testid="asset-inspector">
        {selected ? (
          <Inspector asset={selected} onChanged={onChanged} />
        ) : (
          <div className="inspector-empty">select an asset to inspect it</div>
        )}
      </div>
      <div className="asset-picker">
        {groups.map((s) => (
          <div key={s.title} className="picker-section">
            <div className="picker-title">{s.title}</div>
            <div className="picker-grid">
              {s.assets.map((a) => (
                <button key={a.path} type="button"
                  className={`picker-card ${selected?.path === a.path ? "selected" : ""}`}
                  title={`${a.slug} — ${a.labels.join(", ") || "unlabeled"}`}
                  onClick={() => onSelect(selected?.path === a.path ? null : a)}>
                  {isImage(a)
                    ? <img src={a.url} alt={a.slug} loading="lazy" />
                    : <span className="picker-audio">♪</span>}
                  <span className="picker-name">{a.slug}</span>
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function Inspector({ asset, onChanged }: { asset: AssetItem; onChanged: () => void }) {
  const [labels, setLabels] = useState<string[]>(asset.labels);
  const [draft, setDraft] = useState("");
  const [known, setKnown] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => { setLabels(asset.labels); }, [asset.path, asset.labels]);

  useEffect(() => {
    let alive = true;
    fetchAssets().then((data) => {
      if (!alive) return;
      const all = new Set<string>();
      for (const items of Object.values(data.groups)) {
        for (const a of items) a.labels.forEach((l) => all.add(l));
      }
      setKnown([...all].sort());
    }).catch(() => { /* the datalist just stays empty */ });
    return () => { alive = false; };
  }, [asset.path]);

  const save = async (next: string[]) => {
    setLabels(next);
    try {
      await setAssetLabels(asset.path, next);
      onChanged();
      setError(null);
    } catch (e) {
      setError(String(e));
    }
  };

  return (
    <div className="inspector">
      {isImage(asset)
        ? <img className="inspector-media" src={asset.url} alt={asset.slug} />
        : <audio className="inspector-media" src={asset.url} controls />}
      <div className="inspector-meta">
        <span className="inspector-slug">{asset.slug}</span>
        <span className="inspector-group">{asset.group}</span>
        {asset.used_by.length > 0 && (
          <span className="inspector-used">in {asset.used_by.join(", ")}</span>
        )}
        <a href={asset.url} target="_blank" rel="noreferrer" className="inspector-open">open ↗</a>
      </div>
      <div className="inspector-tags" aria-label={`labels for ${asset.slug}`}>
        {labels.map((l) => (
          <span key={l} className="tag">
            {l}
            <button type="button" aria-label={`remove ${l}`}
              onClick={() => void save(labels.filter((x) => x !== l))}>✕</button>
          </span>
        ))}
        <form className="tag-add" onSubmit={(e) => {
          e.preventDefault();
          const t = draft.trim();
          if (!t || labels.includes(t)) return;
          void save([...labels, t]);
          setDraft("");
        }}>
          <input list="known-labels" value={draft} placeholder="add label…"
            aria-label={`new label for ${asset.slug}`}
            onChange={(e) => setDraft(e.target.value)} />
          <datalist id="known-labels">
            {known.map((l) => <option key={l} value={l} />)}
          </datalist>
          <button type="submit" disabled={!draft.trim()}>add</button>
        </form>
        {error && <span className="tag-error">{error}</span>}
      </div>
    </div>
  );
}
