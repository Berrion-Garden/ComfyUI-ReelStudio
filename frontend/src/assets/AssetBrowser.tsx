import { useEffect, useMemo, useState } from "react";
import { deleteAsset, getProvenance, setAssetLabels, type AssetItem, type AssetsData, type Provenance } from "../api";

interface Props {
  /** the library the app already fetched — known-labels source, no refetch */
  assets: AssetsData | null;
  selected: AssetItem | null;
  /** every picked asset — multi-select turns the display into a carousel */
  selectedList: AssetItem[];
  onChanged: () => void;
  /** deselect after a delete */
  onSelect: (a: AssetItem | null, additive?: boolean) => void;
  /** move the carousel: make another picked asset primary, keep the rest */
  onPrimary: (a: AssetItem) => void;
}

const IMAGE_EXTS = [".png", ".jpg", ".jpeg", ".webp"];

function isImage(a: AssetItem): boolean {
  return IMAGE_EXTS.some((e) => a.url.toLowerCase().endsWith(e));
}

/**
 * The stage's Images view: the highlighted asset, large and interactive —
 * images full-frame, audio a player — with its labels and verify/delete
 * controls. Selection lives in the Assets pane; a multi-selection becomes
 * a carousel (‹ › through everything picked).
 */
export function AssetBrowser({ assets, selected, selectedList,
                               onChanged, onSelect, onPrimary }: Props) {
  const known = useMemo(() => {
    const all = new Set<string>();
    for (const items of Object.values(assets?.groups ?? {})) {
      for (const a of items) a.labels.forEach((l) => all.add(l));
    }
    return [...all].sort();
  }, [assets]);

  const index = selected
    ? selectedList.findIndex((a) => a.path === selected.path) : -1;
  const multi = selectedList.length > 1 && index >= 0;
  const nav = (dir: 1 | -1) => {
    if (!multi) return;
    onPrimary(selectedList[(index + dir + selectedList.length) % selectedList.length]);
  };

  return (
    <div className="asset-stage" data-testid="asset-stage">
      {selected
        ? <div className={`inspector-wrap ${multi ? "carousel" : ""}`}>
            {multi && (
              <>
                <button type="button" className="carousel-nav prev" aria-label="previous picked asset"
                  onClick={() => nav(-1)}>‹</button>
                <button type="button" className="carousel-nav next" aria-label="next picked asset"
                  onClick={() => nav(1)}>›</button>
                <span className="carousel-count">{index + 1} / {selectedList.length}</span>
              </>
            )}
            <Inspector asset={selected} known={known}
              onChanged={onChanged} onSelect={onSelect} />
          </div>
        : <div className="stage-empty">select an asset to inspect it</div>}
    </div>
  );
}

/** The claw-back block: which job made this, with what. Images carry their
 * prompt/seed/models embedded; videos point at the journaled render. */
function Provenance({ path }: { path: string }) {
  const [prov, setProv] = useState<Provenance | null>(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    setProv(null);
    setOpen(false);
    let stale = false;
    getProvenance(path).then((p) => { if (!stale) setProv(p); })
      .catch(() => { if (!stale) setProv(null); });
    return () => { stale = true; };
  }, [path]);

  if (!prov || (!prov.job && !prov.embedded)) return null;
  const e = prov.embedded ?? {};
  const rec = prov.record;
  return (
    <div className="inspector-prov" data-testid="inspector-provenance">
      <button type="button" className="prov-toggle" onClick={() => setOpen((v) => !v)}>
        {open ? "▾" : "▸"} provenance{prov.job ? ` · job ${prov.job}` : ""}
      </button>
      {open && (
        <dl className="prov-fields">
          {rec && (
            <>
              <div><dt>job</dt><dd>{rec.id} · {rec.kind} {rec.target}
                {rec.seed ? ` · seed ${rec.seed}` : ""}</dd></div>
              <div><dt>request</dt><dd>{JSON.stringify(rec.args)}</dd></div>
            </>
          )}
          {Object.entries(e).map(([k, v]) => (
            <div key={k}><dt>{k.replace(/_/g, " ")}</dt><dd title={String(v)}>
              {typeof v === "string" && v.length > 160 ? `${v.slice(0, 160)}…` : String(v)}
            </dd></div>
          ))}
        </dl>
      )}
    </div>
  );
}

function Inspector({ asset, known, onChanged, onSelect }:
  { asset: AssetItem; known: string[]; onChanged: () => void;
    onSelect: (a: AssetItem | null) => void }) {
  const [labels, setLabels] = useState<string[]>(asset.labels);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => { setLabels(asset.labels); }, [asset.path, asset.labels]);

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
        <Provenance path={asset.path} />
        {error && <span className="tag-error">{error}</span>}
      </div>
    </div>
  );
}
