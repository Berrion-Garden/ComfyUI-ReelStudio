import { useEffect, useRef, useState } from "react";
import {
  newScene, openScene, saveScene,
  type StudioScene, type StudioView,
} from "../api";

/** The top-left File menu: save the scene reference, open another scene,
 * create a new one (optionally importing characters/locations). */
export function FileMenu({ studio, onChanged, busy }: {
  studio: StudioView | null;
  onChanged: () => Promise<void>;
  busy: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [slug, setSlug] = useState("");
  const [title, setTitle] = useState("");
  const [source, setSource] = useState<string>("");
  const [picks, setPicks] = useState<{ characters: string[]; backgrounds: string[] }>(
    { characters: [], backgrounds: [] });
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
  const currentScene = studio.scenes.find((s) => s.current);
  const sourceScene = studio.scenes.find((s) => s.slug === source) ?? currentScene;

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

  const togglePick = (kind: "characters" | "backgrounds", name: string) =>
    setPicks((p) => ({
      ...p,
      [kind]: p[kind].includes(name)
        ? p[kind].filter((x) => x !== name)
        : [...p[kind], name],
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
              setSlug("");
              setTitle("");
              setPicks({ characters: [], backgrounds: [] });
            }}>
              ＋ New scene…
            </button>
          )}
          {creating && (
            <div className="file-create">
              <label>slug <input value={slug} placeholder="ep2"
                onChange={(e) => setSlug(e.target.value)} /></label>
              <label>title <input value={title} placeholder="Episode 2"
                onChange={(e) => setTitle(e.target.value)} /></label>
              {studio.saved && sourceScene && (
                <>
                  <div className="file-section">Import from</div>
                  <select value={sourceScene.slug}
                    onChange={(e) => {
                      setSource(e.target.value);
                      setPicks({ characters: [], backgrounds: [] });
                    }}>
                    {studio.scenes.map((s) => (
                      <option key={s.slug} value={s.slug}>{s.title}</option>
                    ))}
                  </select>
                  <PickList kind="characters" scene={sourceScene}
                    picks={picks.characters} onPick={(n) => togglePick("characters", n)} />
                  <PickList kind="backgrounds" scene={sourceScene}
                    picks={picks.backgrounds} onPick={(n) => togglePick("backgrounds", n)} />
                </>
              )}
              <button
                disabled={busy || !slug.trim()}
                onClick={() => void run(() => newScene(
                  slug.trim(), title.trim() || undefined,
                  sourceScene && (picks.characters.length || picks.backgrounds.length)
                    ? { from: sourceScene.slug, ...picks } : undefined))}
              >
                Create scene
              </button>
            </div>
          )}
        </div>
      )}
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

function PickList({ kind, scene, picks, onPick }: {
  kind: "characters" | "backgrounds";
  scene: StudioScene; picks: string[]; onPick: (name: string) => void;
}) {
  const names = scene[kind];
  if (names.length === 0) return null;
  return (
    <div className="file-picks">
      <div className="file-section">{kind} ({picks.length} picked)</div>
      {names.map((n) => (
        <button key={n}
          className={`file-pick ${picks.includes(n) ? "on" : ""}`}
          onClick={() => onPick(n)}>
          {picks.includes(n) ? "☑" : "☐"} {n}
        </button>
      ))}
    </div>
  );
}
