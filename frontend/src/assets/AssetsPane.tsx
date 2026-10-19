import { useEffect, useMemo, useRef, useState } from "react";
import {
  deleteAsset, importAssets, importAudioFromUrl, setAssetLabels, uploadFile,
  type AssetItem, type AssetsData, type StudioView,
} from "../api";

interface Props {
  assets: AssetsData | null;
  /** the studio registry — feeds the cross-scene import list */
  studio: StudioView | null;
  /** the primary selection (what the stage shows) */
  selected: AssetItem | null;
  /** every picked path — shift-click multi-select */
  selectedPaths: Set<string>;
  onSelect: (asset: AssetItem | null, additive?: boolean) => void;
  /** called after a verify/delete so the app refetches the library */
  onChanged: () => void;
}

/** Groups a section's assets by their `<prefix>:<slug>` label into
 * subsections — character pools (`char:`) and location pools (`loc:`). */
function labeledPools(items: AssetItem[], prefix: string): { pool: string; assets: AssetItem[] }[] {
  const pools = new Map<string, AssetItem[]>();
  for (const a of items) {
    const label = a.labels.find((l) => l.startsWith(prefix)) ?? `${prefix}unsorted`;
    if (!pools.has(label)) pools.set(label, []);
    pools.get(label)!.push(a);
  }
  return [...pools.entries()].map(([pool, assets]) => ({ pool: pool.slice(prefix.length), assets }));
}

/** One character's collapsible pool: reference (the operator's uploaded
 * base images) and posed stills (generated), each collapsible on its own.
 * `closed` holds keys the user collapsed — defaults open, and the periodic
 * asset refresh can't snap them back. */
function CharacterPool({ name, assets, card, openKey, closed, onToggle }: {
  name: string; assets: AssetItem[]; card: (a: AssetItem) => React.ReactNode;
  openKey: string; closed: Set<string>; onToggle: (key: string) => void;
}) {
  const refs = assets.filter((a) => a.labels.includes("reference"));
  const posed = assets.filter((a) => a.labels.includes("posed"));
  // legacy unlabeled assets (pre-split files without set labels) read as
  // reference — they are the operator's uploaded material
  const loose = assets.filter(
    (a) => !a.labels.includes("reference") && !a.labels.includes("posed"));
  const toggle = (key: string) => (e: React.SyntheticEvent<HTMLDetailsElement>) => {
    if (e.currentTarget.open === closed.has(key)) onToggle(key);
  };
  const sub = (kind: string, items: AssetItem[]) => (
    <details className="pool-sub" open={!closed.has(`${openKey}/${kind}`)}
      onToggle={toggle(`${openKey}/${kind}`)}>
      <summary>{kind} <span className="count">{items.length}</span></summary>
      <div className="asset-grid">{items.map(card)}</div>
    </details>
  );
  return (
    <details className="asset-pool" open={!closed.has(openKey)}
      onToggle={toggle(openKey)}>
      <summary>{name} <span className="count">{assets.length}</span></summary>
      {sub("reference", [...refs, ...loose])}
      {sub("posed stills", posed)}
    </details>
  );
}

// where the section's + / drag-and-drop uploads land (workspace-relative);
// pool sections (Characters, Backgrounds) ask for the pool/location name
// first and append it
const UPLOAD_DIRS: Record<string, string> = {
  "Characters": "characters",
  "Backgrounds": "backgrounds",
  "Custom": "images",
  "Audio": "audio",
  "Sound FX": "sfx",
};
const POOL_SECTIONS = new Set(["Characters", "Backgrounds"]);

/** A drop on the pane background lands by extension: images in Custom,
 * audio in Audio. Sections carry their own dir. */
function dropTitle(files: FileList): string {
  const audio = [".mp3", ".wav", ".ogg", ".flac", ".m4a"];
  const one = files[0];
  return one && audio.some((e) => one.name.toLowerCase().endsWith(e))
    ? "Audio" : "Custom";
}

export function AssetsPane({ assets, studio, selected, selectedPaths, onSelect, onChanged }: Props) {
  const data = assets;
  const [menuFor, setMenuFor] = useState<string | null>(null);
  const [copied, setCopied] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [poolForm, setPoolForm] = useState<string | null>(null);
  const [poolName, setPoolName] = useState("unsorted");
  const [uploading, setUploading] = useState(0);
  const [charPanel, setCharPanel] = useState(false);
  const [urlForm, setUrlForm] = useState(false);
  const [urlValue, setUrlValue] = useState("");
  const [grabbing, setGrabbing] = useState(false);
  const [importSrc, setImportSrc] = useState<{ scene: string; pool: string } | null>(null);
  const [importTarget, setImportTarget] = useState("");
  const fileInput = useRef<HTMLInputElement | null>(null);
  const uploadTitle = useRef<string>("");

  const pick = (title: string) => {
    if (title === "Characters") {
      setCharPanel((v) => !v);  // upload or import from another scene
      return;
    }
    if (POOL_SECTIONS.has(title)) {
      setPoolForm((v) => (v === title ? null : title));  // the pool needs a name before the picker
      return;
    }
    uploadTitle.current = title;
    fileInput.current?.click();
  };

  const chooseFiles = (section: string) => {
    setPoolForm(null);
    setCharPanel(false);
    uploadTitle.current = section;
    fileInput.current?.click();
  };

  const importPool = () => {
    if (!importSrc || !importTarget.trim()) return;
    void act(() => importAssets({
      from: importSrc.scene,
      characters: [importSrc.pool],
      backgrounds: [],
      as: importTarget.trim(),
    }));
    setImportSrc(null);
    setImportTarget("");
  };

  // every character pool living in another scene, newest scene last
  const otherPools = useMemo(() => (studio?.scenes ?? [])
    .filter((s) => !s.current)
    .flatMap((s) => s.characters.map((pool) => ({
      scene: s.slug, title: s.title, pool,
    }))), [studio]);

  const upload = async (files: FileList | File[]) => {
    const title = uploadTitle.current;
    const base = UPLOAD_DIRS[title];
    if (!base || files.length === 0) return;
    const dir = POOL_SECTIONS.has(title)
      ? `${base}/${poolName.trim() || "unsorted"}` : base;
    setUploading((n) => n + files.length);
    setError(null);
    try {
      for (const f of Array.from(files)) {
        await uploadFile(f, dir);
      }
      onChanged();
    } catch (e) {
      setError(String(e));
    } finally {
      setUploading((n) => Math.max(0, n - files.length));
    }
  };

  const grabUrl = async () => {
    const url = urlValue.trim();
    if (!url || grabbing) return;
    setGrabbing(true);
    setError(null);
    try {
      await importAudioFromUrl(url);
      setUrlForm(false);
      setUrlValue("");
      onChanged();
    } catch (e) {
      setError(String(e));
    } finally {
      setGrabbing(false);
    }
  };

  useEffect(() => {
    if (!menuFor) return;
    const close = () => setMenuFor(null);
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [menuFor]);

  const sections = useMemo(() => {
    if (!data) return [];
    const g = data.groups;
    const out: { title: string; assets: AssetItem[] }[] = [
      { title: "Characters", assets: g.characters },
      { title: "Scenes", assets: g.scenes },
      { title: "New stills", assets: g.stills ?? [] },
      { title: "Backgrounds", assets: g.backgrounds ?? [] },
      { title: "Custom", assets: g.custom },
      { title: "LORA / Theme", assets: g.themes },
      { title: "Audio", assets: g.audio },
      { title: "Sound FX", assets: g.sfx },
    ];
    return out;
  }, [data]);

  // controlled, so the periodic asset refresh re-rendering this pane can't
  // snap the user's collapsed sections back open
  const [openSections, setOpenSections] = useState<Set<string>>(
    () => new Set(["Characters", "Scenes"]));
  // character pools + their reference/posed-stills sub-pools: `closed`
  // holds keys the user collapsed — everything defaults open, and the
  // periodic asset refresh can't snap them back open
  const [closedPools, setClosedPools] = useState<Set<string>>(() => new Set());
  const toggleClosedPool = (key: string) =>
    setClosedPools((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key); else next.add(key);
      return next;
    });
  const setOpen = (title: string, open: boolean) =>
    setOpenSections((prev) => {
      if (prev.has(title) === open) return prev;
      const next = new Set(prev);
      if (open) next.add(title); else next.delete(title);
      return next;
    });

  // flat order for arrow-key navigation, top to bottom
  const flat = useMemo(() => sections.flatMap((s) => s.assets), [sections]);

  const move = (dir: 1 | -1) => {
    if (flat.length === 0) return;
    const idx = selected ? flat.findIndex((a) => a.path === selected.path) : -1;
    const next = flat[Math.min(Math.max(idx + dir, 0), flat.length - 1)];
    if (next) onSelect(next);
  };

  const act = async (fn: () => Promise<unknown>) => {
    setError(null);
    try {
      await fn();
      onChanged();
    } catch (e) {
      setError(String(e));
    }
  };

  const accept = (a: AssetItem) =>
    void act(() => setAssetLabels(
      a.path, a.labels.filter((l) => l !== "non-verified")));
  const remove = (a: AssetItem) =>
    void act(() => deleteAsset(a.path));
  const copyReference = async (a: AssetItem) => {
    // the agent's unique id: `asset:<path>` resolves through get_assets /
    // currently_selected
    await navigator.clipboard.writeText(`asset:${a.path}`);
    setCopied(a.path);
    setTimeout(() => setCopied((c) => (c === a.path ? null : c)), 1500);
  };

  const card = (a: AssetItem) => {
    const isImage = !a.url.endsWith(".mp3") && !a.url.endsWith(".wav");
    const isSel = selected?.path === a.path;
    const isPicked = selectedPaths.has(a.path);
    const unverified = a.labels.includes("non-verified");
    return (
        <div
          key={a.path}
          role="button"
          tabIndex={-1}
          className={`asset-card ${isSel ? "selected" : ""} ${isPicked ? "picked" : ""}`}
          onClick={(e) => onSelect(a, e.shiftKey)}
          title={`${a.slug}\n${a.labels.join(" · ")}${a.used_by.length ? `\nused by: ${a.used_by.join(", ")}` : ""}\n\nshift-click: add to selection`}
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
          {unverified && (
            <span className="card-verify" onClick={(e) => e.stopPropagation()}>
              <button type="button" className="verify-ok" title="keep — accept this image"
                aria-label={`accept ${a.slug}`} onClick={() => accept(a)}>✓</button>
              <button type="button" className="verify-del" title="delete this image"
                aria-label={`delete ${a.slug}`} onClick={() => remove(a)}>✕</button>
            </span>
          )}
          <button type="button" className="card-menu-btn" title="more actions"
            aria-label={`actions for ${a.slug}`}
            onClick={(e) => { e.stopPropagation(); setMenuFor(menuFor === a.path ? null : a.path); }}
          >⋯</button>
          {menuFor === a.path && (
            <span className="card-menu" onClick={(e) => e.stopPropagation()}>
              <button type="button" onClick={() => { void copyReference(a); setMenuFor(null); }}>
                {copied === a.path ? "copied ✓" : "Copy reference"}
              </button>
              <button type="button" onClick={() => { remove(a); setMenuFor(null); }}>
                Delete
              </button>
            </span>
          )}
        </div>
    );
  };

  return (
    <div className="assets-pane" data-testid="assets-pane"
      tabIndex={0}
      aria-label="asset library"
      onDragOver={(e) => { if (e.dataTransfer.types.includes("Files")) e.preventDefault(); }}
      onDrop={(e) => {
        if (e.dataTransfer.files.length === 0) return;
        e.preventDefault();
        uploadTitle.current = dropTitle(e.dataTransfer.files);
        void upload(e.dataTransfer.files);
      }}
      onKeyDown={(e) => {
        if (e.key === "ArrowDown") { e.preventDefault(); move(1); }
        if (e.key === "ArrowUp") { e.preventDefault(); move(-1); }
      }}>
      <div className="assets-header">Assets</div>
      {!data && <div className="assets-loading">loading assets…</div>}
      {error && <div className="assets-error" onClick={() => setError(null)}>{error}</div>}
      {sections.map((s) => (
        <details key={s.title} className="asset-section"
          open={openSections.has(s.title)}
          onToggle={(e) => setOpen(s.title, e.currentTarget.open)}
          onDragOver={(e) => { if (UPLOAD_DIRS[s.title]) e.preventDefault(); }}
          onDrop={(e) => {
            // a drop uploads into this section's library dir
            const base = UPLOAD_DIRS[s.title];
            if (!base || e.dataTransfer.files.length === 0) return;
            e.preventDefault(); e.stopPropagation();
            uploadTitle.current = s.title;
            if (POOL_SECTIONS.has(s.title)) setPoolName("unsorted");
            void upload(e.dataTransfer.files);
          }}>
          <summary>
            {s.title} <span className="count">{s.assets.length}</span>
            {UPLOAD_DIRS[s.title] && (
              <button type="button" className="section-upload" title="upload files here"
                aria-label={`upload into ${s.title}`}
                onClick={(e) => { e.preventDefault(); e.stopPropagation(); pick(s.title); }}
                disabled={uploading > 0}
              >{uploading > 0 ? `↑${uploading}` : "+"}</button>
            )}
            {s.title === "Audio" && (
              <button type="button" className="section-upload" title="grab a track from a URL (YouTube, …)"
                aria-label="grab audio from URL"
                onClick={(e) => { e.preventDefault(); e.stopPropagation(); setUrlForm((v) => !v); }}
                disabled={grabbing}
              >{grabbing ? "↧" : "⇩"}</button>
            )}
            {s.title === "Backgrounds" && poolForm === s.title && (
              <span className="pool-form" onClick={(e) => e.stopPropagation()}>
                <input value={poolName} autoFocus
                  onChange={(e) => setPoolName(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter") chooseFiles(s.title); }}
                  placeholder="location name"
                  aria-label={`${s.title.toLowerCase()} pool name`} />
                <button type="button" onClick={() => chooseFiles(s.title)}>choose files…</button>
              </span>
            )}
          </summary>
          {s.title === "Characters" && charPanel && (
            <div className="char-panel" onClick={(e) => e.stopPropagation()}>
              <div className="import-list">
                {otherPools.length === 0 && (
                  <div className="file-muted">no pools in other scenes yet</div>
                )}
                {otherPools.map(({ scene, title: st, pool }) => {
                  const on = importSrc?.scene === scene && importSrc?.pool === pool;
                  return (
                    <button key={`${scene}/${pool}`} type="button"
                      className={on ? "on" : ""}
                      title={`import ${pool} from ${st}`}
                      onClick={() => {
                        setImportSrc({ scene, pool });
                        setImportTarget(pool);
                      }}>
                      {st} · {pool}
                    </button>
                  );
                })}
              </div>
              <span className="pool-form">
                <input value={importTarget} placeholder="into pool"
                  aria-label="import target pool name"
                  onChange={(e) => setImportTarget(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter") importPool(); }} />
                <button type="button" disabled={!importSrc || !importTarget.trim()}
                  onClick={importPool}>Import</button>
              </span>
              <span className="pool-form">
                <input value={poolName}
                  onChange={(e) => setPoolName(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter") chooseFiles("Characters"); }}
                  placeholder="pool name" aria-label="character pool name" />
                <button type="button" onClick={() => chooseFiles("Characters")}>
                  choose files…
                </button>
              </span>
            </div>
          )}
          {s.title === "Audio" && urlForm && (
            <div className="char-panel" onClick={(e) => e.stopPropagation()}>
              <span className="pool-form">
                <input value={urlValue} autoFocus
                  onChange={(e) => setUrlValue(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter") void grabUrl(); }}
                  placeholder="https://www.youtube.com/watch?v=…"
                  aria-label="audio source URL" />
                <button type="button" disabled={!urlValue.trim() || grabbing}
                  onClick={() => void grabUrl()}>Grab</button>
              </span>
            </div>
          )}
          {POOL_SECTIONS.has(s.title) && s.assets.length > 0 ? (
            labeledPools(s.assets, s.title === "Characters" ? "char:" : "loc:")
              .map(({ pool, assets }) =>
              s.title === "Characters" ? (
                <CharacterPool key={pool} name={pool}
                  openKey={`Characters/${pool}`}
                  closed={closedPools} onToggle={toggleClosedPool}
                  card={card} assets={assets} />
              ) : (
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
      <input ref={fileInput} type="file" multiple hidden
        onChange={(e) => {
          if (e.target.files?.length) void upload(e.target.files);
          e.target.value = "";  // allow re-picking the same files
        }} />
    </div>
  );
}
