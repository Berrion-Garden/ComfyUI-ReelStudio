import { useCallback, useEffect, useState } from "react";
import { assemble, fetchProject, renderScenes, renderStale } from "./api";
import { Player } from "./player/Player";
import { Timeline } from "./timeline/Timeline";
import { Chat } from "./chat/Chat";
import type { ProjectView } from "./types";

export function App() {
  const [project, setProject] = useState<ProjectView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [playheadPct, setPlayheadPct] = useState<number | null>(null);
  const [busyAction, setBusyAction] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setProject(await fetchProject());
      setError(null);
    } catch (e) {
      setError(String(e));
    }
  }, []);

  useEffect(() => {
    void refresh();
    const timer = setInterval(() => { void refresh(); }, 3000);
    return () => clearInterval(timer);
  }, [refresh]);

  const act = async (name: string, fn: () => Promise<void>) => {
    setBusyAction(name);
    try {
      await fn();
      await refresh();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusyAction(null);
    }
  };

  if (error && !project) {
    return <div className="app-error">Reel Studio: {error}</div>;
  }
  if (!project) {
    return <div className="app-loading">Loading reel…</div>;
  }

  const artifactUrl = (sceneId: string, kind: string) =>
    `/reelstudio/api/scene/${sceneId}/artifact/${kind}`;

  const anyJobsRunning = project.jobs.some((j) => j.status === "queued" || j.status === "running");

  return (
    <div className="app">
      <header className="app-header">
        <h1>Reel Studio</h1>
        <div className="app-meta">
          {project.scenes.length} scenes · {project.total_s.toFixed(1)}s ·{" "}
          {project.fps} fps
        </div>
        <div className="app-actions">
          <button
            onClick={() => void act("render-stale", renderStale)}
            disabled={busyAction !== null || anyJobsRunning}
            title="re-render every changed scene (and its prev_last chain)"
          >
            ⟳ Render changed
          </button>
          <button
            onClick={() => void act("assemble", () => assemble(false))}
            disabled={busyAction !== null || anyJobsRunning}
            title="final production: music bed + concat + mix"
          >
            🎬 Final production
          </button>
        </div>
      </header>

      {error && <div className="app-error" onClick={() => setError(null)}>{error} (click to dismiss)</div>}
      {anyJobsRunning && <div className="job-banner">jobs running…</div>}

      <main className="app-main">
        <Timeline
          scenes={project.scenes}
          music={project.music}
          totalS={project.total_s}
          artifactUrl={artifactUrl}
          playheadPct={playheadPct}
          onRenderScene={(id) => void act(`render:${id}`, () => renderScenes([id]))}
        />
        <Player
          scenes={project.scenes}
          onPlayhead={setPlayheadPct}
        />
      </main>

      <Chat onProjectChanged={() => void refresh()} />
    </div>
  );
}
