import { useEffect, useState } from "react";
import { deleteAsset, fetchAssets, setAssetLabels,
  type AssetItem } from "../api";

interface Props {
  selected: AssetItem | null;
  onChanged: () => void;
  /** deselect after a delete */
  onSelect: (a: AssetItem | null) => void;
}

const IMAGE_EXTS = [".png", ".jpg", ".jpeg", ".webp"];

function isImage(a: AssetItem): boolean {
  return IMAGE_EXTS.some((e) => a.url.toLowerCase().endsWith(e));
}

/**
 * The stage's Images view: the single highlighted asset, large and
 * interactive — images full-frame, audio a player — with its labels and
 * verify/delete controls. Selection lives in the Assets pane.
 */
export function AssetBrowser({ selected, onChanged, onSelect }: Props) {
  return (
    <div className="asset-stage" data-testid="asset-stage">
      {selected
        ? <Inspector asset={selected} onChanged={onChanged} onSelect={onSelect} />
        : <div className="stage-empty">select an asset to inspect it</div>}
    </div>
  );
}

function Inspector({ asset, onChanged, onSelect }:
  { asset: AssetItem; onChanged: () => void; onSelect: (a: AssetItem | null) => void }) {
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

  const approve = () => void save(labels.filter((l) => l !== "non-verified"));

  const remove = async () => {
    try {
      await deleteAsset(asset.path);
      setError(null);
      onSelect(null);
      onChanged();
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
        {labels.includes("non-verified") && (
          <span className="verify-row">
            <button type="button" className="verify-ok" aria-label={`verify ${asset.slug}`}
              title="keep — removes the non-verified label"
              onClick={approve}>✓</button>
            <button type="button" className="verify-del" aria-label={`delete ${asset.slug}`}
              title="delete this image"
              onClick={() => void remove()}>✕</button>
          </span>
        )}
        {error && <span className="tag-error">{error}</span>}
      </div>
    </div>
  );
}
