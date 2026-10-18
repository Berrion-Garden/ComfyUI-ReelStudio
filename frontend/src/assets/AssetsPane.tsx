import { useEffect, useMemo, useRef, useState } from "react";
import { deleteAsset, setAssetLabels, uploadFile, type AssetItem, type AssetsData } from "../api";

interface Props {
  assets: AssetsData | null;
  /** the primary selection (what the stage shows) */
  selected: AssetItem | null;
  /** every picked path — shift-click multi-select */
  selectedPaths: Set<string>;
  onSelect: (asset: AssetItem | null, additive?: boolean) => void;
  /** called after a verify/delete so the app refetches the library */
  onChanged: () => void;
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

// where the section's + / drag-and-drop uploads land (workspace-relative);
// the Characters section appends the pool name at upload time
const UPLOAD_DIRS: Record<string, string> = {
  "Characters": "characters",
  "Backgrounds": "backgrounds",
  "Custom": "images",
  "Audio": "audio",
  "Sound FX": "sfx",
};

/** A drop on the pane background lands by extension: images in Custom,
 * audio in Audio. Sections carry their own dir. */
function dropTitle(files: FileList): string {
  const audio = [".mp3", ".wav", ".ogg", ".flac", ".m4a"];
  const one = files[0];
  return one && audio.some((e) => one.name.toLowerCase().endsWith(e))
    ? "Audio" : "Custom";
}

export function AssetsPane({ assets, selected, selectedPaths, onSelect, onChanged }: Props) {
  const data = assets;
  const [menuFor, setMenuFor] = useState<string | null>(null);
  const [copied, setCopied] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [poolForm, setPoolForm] = useState(false);
  const [poolName, setPoolName] = useState("unsorted");
  const [uploading, setUploading] = useState(0);
  const fileInput = useRef<HTMLInputElement | null>(null);
  const uploadTitle = useRef<string>("");

  const pick = (title: string) => {
    if (title === "Characters") {
      setPoolForm((v) => !v);  // the pool needs a name before the picker
      return;
    }
    uploadTitle.current = title;
    fileInput.current?.click();
  };

  const chooseFiles = () => {
    setPoolForm(false);
    uploadTitle.current = "Characters";
    fileInput.current?.click();
  };

  const upload = async (files: FileList | File[]) => {
    const title = uploadTitle.current;
    const base = UPLOAD_DIRS[title];
    if (!base || files.length === 0) return;
    const dir = title === "Characters"
      ? `characters/${poolName.trim() || "unsorted"}` : base;
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

  useEffect(() => {
    if (!menuFor) return;
    const close = () => setMenuFor(null);
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [menuFor]);

  const sections = useMemo(() => {
    if (!data) return [];
    const g = data.groups;
    const out: { title: string; open: boolean; assets: AssetItem[] }[] = [
      { title: "Characters", open: true, assets: g.characters },
      { title: "Scenes", open: true, assets: g.scenes },
      { title: "New stills", open: false, assets: g.stills ?? [] },
      { title: "Backgrounds", open: false, assets: g.backgrounds ?? [] },
      { title: "Custom", open: false, assets: g.custom },
      { title: "LORA / Theme", open: false, assets: g.themes },
      { title: "Audio", open: false, assets: g.audio },
      { title: "Sound FX", open: false, assets: g.sfx },
    ];
    return out;
  }, [data]);

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
        <details key={s.title} className="asset-section" open={s.open}
          onDragOver={(e) => { if (UPLOAD_DIRS[s.title]) e.preventDefault(); }}
          onDrop={(e) => {
            // a drop uploads into this section's library dir
            const base = UPLOAD_DIRS[s.title];
            if (!base || e.dataTransfer.files.length === 0) return;
            e.preventDefault(); e.stopPropagation();
            uploadTitle.current = s.title;
            if (s.title === "Characters") setPoolName("unsorted");
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
            {s.title === "Characters" && poolForm && (
              <span className="pool-form" onClick={(e) => e.stopPropagation()}>
                <input value={poolName} autoFocus
                  onChange={(e) => setPoolName(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter") chooseFiles(); }}
                  placeholder="pool name" aria-label="character pool name" />
                <button type="button" onClick={chooseFiles}>choose files…</button>
              </span>
            )}
          </summary>
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
      <input ref={fileInput} type="file" multiple hidden
        onChange={(e) => {
          if (e.target.files?.length) void upload(e.target.files);
          e.target.value = "";  // allow re-picking the same files
        }} />
    </div>
  );
}
