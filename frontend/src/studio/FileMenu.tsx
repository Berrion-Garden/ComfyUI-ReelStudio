import { useEffect, useRef, useState } from "react";
import {
  newScene, openScene, saveScene,
  type StudioScene, type StudioView,
} from "../api";

const slugify = (s: string) =>
  s.toLowerCase().replace(/['’]/g, "")
    .replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");

/** The top-left File menu: save the scene reference, open another scene,
 * create a new one (title-first — the slug derives from the title unless
 * overridden). */
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

  const create = () => {
    const finalSlug = slug.trim() || slugify(title);
    if (!finalSlug) return;
    void run(() => newScene(finalSlug, title.trim() || undefined));
  };

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
            }}>
              ＋ New scene…
            </button>
          )}
          {creating && (
            <div className="file-create">
              <label>title <input value={title} placeholder="Episode 2"
                onChange={(e) => setTitle(e.target.value)} /></label>
              <label>slug <input value={slug}
                placeholder={slugify(title) || "ep2"}
                onChange={(e) => setSlug(e.target.value)} /></label>
              <button
                disabled={busy || !(slug.trim() || slugify(title))}
                onClick={create}>
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
