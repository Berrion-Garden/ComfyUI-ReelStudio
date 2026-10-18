import { useEffect, useRef, useState } from "react";
import {
  newScene, openScene, saveScene,
  type ImportSpec, type StudioScene, type StudioView,
} from "../api";

type PoolKind = "characters" | "backgrounds";
const emptyPicks = (): Record<PoolKind, string[]> =>
  ({ characters: [], backgrounds: [] });

/** The top-left File menu: save the scene reference, open another scene,
 * create a new one from its name alone (the slug derives server-side).
 * Importing pools from another scene is opt-in. */
export function FileMenu({ studio, onChanged, busy }: {
  studio: StudioView | null;
  onChanged: () => Promise<void>;
  busy: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [title, setTitle] = useState("");
  const [importing, setImporting] = useState(false);
  const [source, setSource] = useState("");
  const [picks, setPicks] = useState(emptyPicks);
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) {
        setOpen(false);
        setCreating(false);
      }
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);

  if (!studio) return null;

  const run = async (fn: () => Promise<unknown>) => {
    setError(null);
    try {
      await fn();
      await onChanged();
      setOpen(false);
      setCreating(false);
    } catch (e) {
      setError(String(e));
    }
  };

  const from = studio.scenes.find((s) => s.slug === source)
    ?? studio.scenes.find((s) => s.current);

  const importSpec = (): ImportSpec | undefined => {
    if (!importing || !from) return undefined;
    if (!picks.characters.length && !picks.backgrounds.length) return undefined;
    return { from: from.slug, ...picks };
  };

  const create = () => {
    if (!title.trim()) return;
    void run(() => newScene(title.trim(), importSpec()));
  };

  const togglePool = (kind: PoolKind, pool: string) =>
    setPicks((p) => ({
      ...p,
      [kind]: p[kind].includes(pool)
        ? p[kind].filter((x) => x !== pool)
        : [...p[kind], pool],
    }));

  return (
    <div className="file-menu" ref={ref}>
      <button
        className={`file-button ${open ? "on" : ""}`}
        onClick={() => setOpen(!open)}
        title="save, open, or create scenes"
      >
        File <span className="chevron">{open ? "▴" : "▾"}</span>
      </button>
      {open && (
        <div className="file-dropdown">
          {error && <div className="file-error">{error}</div>}
          <button
            disabled={busy}
            onClick={() => void run(() => saveScene())}
            title={studio.saved
              ? "persist the current scene as the studio's open scene"
              : "save this project as a named scene (moves it into scenes/)"}
          >
            💾 Save scene
          </button>
          <div className="file-section">Open scene</div>
          {studio.scenes.map((s) => (
            <SceneRow key={s.slug} scene={s}
              onOpen={() => void run(() => openScene(s.slug))} busy={busy} />
          ))}
          {!creating && (
            <button disabled={busy} onClick={() => {
              setCreating(true);
              setTitle("");
              setImporting(false);
              setSource("");
              setPicks(emptyPicks());
            }}>
              ＋ New scene…
            </button>
          )}
          {creating && (
            <div className="file-create">
              <label>name <input value={title} placeholder="Episode 2"
                autoFocus
                onChange={(e) => setTitle(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && create()} /></label>
              {studio.saved && (
                <label className="file-import-toggle">
                  <input type="checkbox" checked={importing}
                    onChange={(e) => {
                      setImporting(e.target.checked);
                      setPicks(emptyPicks());
                    }} />
                  bring in characters & locations
                </label>
              )}
              {importing && studio.saved && (
                <div className="file-import">
                  <select value={from?.slug ?? ""}
                    onChange={(e) => {
                      setSource(e.target.value);
                      setPicks(emptyPicks());
                    }}>
                    {studio.scenes.map((s) => (
                      <option key={s.slug} value={s.slug}>{s.title}</option>
                    ))}
                  </select>
                  <PoolRow label="characters" pools={from?.characters ?? []}
                    picked={picks.characters}
                    onToggle={(p) => togglePool("characters", p)} />
                  <PoolRow label="locations" pools={from?.backgrounds ?? []}
                    picked={picks.backgrounds}
                    onToggle={(p) => togglePool("backgrounds", p)} />
                </div>
              )}
              <button disabled={busy || !title.trim()} onClick={create}>
                Create scene
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function PoolRow({ label, pools, picked, onToggle }: {
  label: string;
  pools: string[];
  picked: string[];
  onToggle: (pool: string) => void;
}) {
  return (
    <div className="file-pools">
      <span>{label}</span>
      {pools.map((p) => (
        <button key={p} className={picked.includes(p) ? "on" : ""}
          onClick={() => onToggle(p)}>{p}</button>
      ))}
      {pools.length === 0 && <span className="file-muted">none</span>}
    </div>
  );
}

function SceneRow({ scene, onOpen, busy }: {
  scene: StudioScene; onOpen: () => void; busy: boolean;
}) {
  return (
    <button className={`file-scene ${scene.current ? "current" : ""}`}
      disabled={busy || scene.current}
      onClick={onOpen}
      title={scene.current ? "the open scene" : `open ${scene.title}`}>
      {scene.current ? "✓ " : "　"}{scene.title}
    </button>
  );
}
