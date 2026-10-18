import { useCallback, useEffect, useRef, useState } from "react";
import { adoptRenders, assemble, bellUrl, fetchAssets, fetchProject, fetchSfxBoard, renderScenes, renderStale, updateAudioTrack, placeSfxEvent, removeSfxEvent, type AssetItem, type AssetsData, type SfxScene } from "./api";
import { Player } from "./player/Player";
import { AssetBrowser } from "./assets/AssetBrowser";
import { Timeline } from "./timeline/Timeline";
import { Chat } from "./chat/Chat";
import { AssetsPane } from "./assets/AssetsPane";
import type { ProjectView } from "./types";

export function App() {
  const [project, setProject] = useState<ProjectView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [playheadPct, setPlayheadPct] = useState<number | null>(null);
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [selectedAsset, setSelectedAsset] = useState<AssetItem | null>(null);
  const [assets, setAssets] = useState<AssetsData | null>(null);
  const [seekRequest, setSeekRequest] = useState<{ s: number; n: number } | null>(null);
  const [sfxBoard, setSfxBoard] = useState<SfxScene[]>([]);
  const [stageView, setStageView] = useState<"player" | "images">("player");
  const stageRef = useRef<HTMLElement | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [p, board, lib] = await Promise.all([
        fetchProject(),
        fetchSfxBoard().catch(() => [] as SfxScene[]),
        fetchAssets().catch(() => null),
      ]);
      setProject(p);
      setSfxBoard(board);
      if (lib) {
        setAssets(lib);
        // keep the selection in step with the library (labels refresh, and a
        // regenerated asset may have been replaced on disk)
        setSelectedAsset((sel) =>
          sel ? lib.groups[sel.group]?.find((a) => a.path === sel.path) ?? null : null);
      }
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

  const seekTo = (pct: number) => {
    if (!project || project.total_s <= 0) return;
    setSeekRequest({ s: (pct / 100) * project.total_s, n: Date.now() });
  };

  const toggleFullscreen = () => {
    const el = stageRef.current;
    if (!el) return;
    if (document.fullscreenElement) {
      void document.exitFullscreen();
    } else {
      void el.requestFullscreen().catch((e) => setError(String(e)));
    }
  };

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
            onClick={() => void act("adopt", adoptRenders)}
            disabled={busyAction !== null || anyJobsRunning}
            title="declare the current renders match this config (no re-render)"
          >
            ✓ Adopt renders
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
        <div className="app-top">
          <section className="stage-pane" aria-label="preview" ref={stageRef}>
            <div className="stage-tabs">
              <button type="button" className={stageView === "player" ? "tab on" : "tab"}
                onClick={() => setStageView("player")}>▶ Player</button>
              <button type="button" className={stageView === "images" ? "tab on" : "tab"}
                onClick={() => setStageView("images")}>🖼 Images</button>
              <span className="stage-tabs-spacer" />
              <button type="button" onClick={toggleFullscreen}
                title="fullscreen the player">⛶</button>
            </div>
            <div className={stageView === "player" ? "stage-host" : "stage-host hidden"}>
              <Player
                scenes={project.scenes}
                onPlayhead={setPlayheadPct}
                selectedAsset={selectedAsset
                  ? { url: selectedAsset.url, name: selectedAsset.slug }
                  : null}
                seekRequest={seekRequest}
              mix={{
                // the real tracks always; the Music3 bed only when the mix
                // uses it (skip_music: false) — mirrors reel.py assemble
                sources: [
                  ...project.overlays
                    .filter((o) => o.present && o.url)
                    .map((o) => ({
                      key: `a${o.index}`, url: o.url as string,
                      startS: o.start_s, durS: o.duration_s,
                      gain: o.gain, seek: o.seek, fades: o.fades,
                    })),
                  ...(!(project.flags as { skip_music?: boolean }).skip_music
                    ? project.music
                        .filter((m) => m.present && m.url)
                        .map((m, i) => ({
                          key: `m${i}`, url: m.url as string,
                          startS: m.start_s, durS: m.duration_s,
                          gain: m.gain, seek: 0, fades: [],
                        }))
                    : []),
                ],
                sfxVolume: project.sfx_volume,
                useMusic: !(project.flags as { skip_music?: boolean }).skip_music,
                oneShots: [
                  // placed sfx-board events, at absolute reel time
                  ...sfxBoard.flatMap((row) => {
                    const sc = project.scenes.find((s) => s.id === row.id);
                    return row.assets
                      .filter((a) => a.url)
                      .map((a, i) => ({
                        key: `${row.id}#${i}`, url: a.url as string,
                        atS: (sc?.start_s ?? 0) + a.at, gain: a.gain,
                      }));
                  }),
                  // the yaml bell is just a well-known one-shot asset
                  ...project.scenes
                    .filter((s) => s.bell_at !== null)
                    .map((s) => ({
                      key: `bell-${s.id}`, url: bellUrl(),
                      atS: s.start_s + (s.bell_at as number), gain: 0.5,
                    })),
                ],
                totalS: project.total_s,
              }}
              />
            </div>
            <div className={stageView === "images" ? "stage-host" : "stage-host hidden"}>
              <AssetBrowser assets={assets} selected={selectedAsset}
                onSelect={setSelectedAsset} onChanged={() => void refresh()} />
            </div>
          </section>
          <AssetsPane assets={assets} selected={selectedAsset}
            onSelect={setSelectedAsset} />
        </div>
        <Timeline
          scenes={project.scenes}
          music={project.music}
          overlays={project.overlays}
          sfxRows={sfxBoard}
          onPlaceSfx={(sceneId, asset, at) => {
            void placeSfxEvent(sceneId, asset, at)
              .then(() => refresh())
              .catch((e) => setError(String(e)));
          }}
          onRemoveSfx={(sceneId, index) => {
            void removeSfxEvent(sceneId, index)
              .then(() => refresh())
              .catch((e) => setError(String(e)));
          }}
          onTrackChange={(index, fades) => {
            void updateAudioTrack(index, { fades })
              .then(() => refresh())
              .catch((e) => setError(String(e)));
          }}
          totalS={project.total_s}
          artifactUrl={artifactUrl}
          playheadPct={playheadPct}
          onSeek={seekTo}
          onRenderScene={(id) => void act(`render:${id}`, () => renderScenes([id]))}
        />
      </main>

      <Chat onProjectChanged={() => void refresh()}
        selected={selectedAsset
          ? { slug: selectedAsset.slug, path: selectedAsset.path,
              group: selectedAsset.group, labels: selectedAsset.labels }
          : null} />
    </div>
  );
}
