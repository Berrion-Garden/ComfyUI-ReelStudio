import { useEffect, useRef, useState } from "react";
import type { SceneView } from "../types";
import { absoluteTime, advance, createQueue, type Clip } from "./queue";

interface Props {
  scenes: SceneView[];
  onPlayhead?: (pct: number | null) => void;
}

/**
 * Plays the chain seamlessly without concatenating: two <video> elements
 * trade off — while one plays, the next scene's clip preloads in the other,
 * and the swap happens at the boundary. The reel ends only at a XXX scene.
 */
export function Player({ scenes, onPlayhead }: Props) {
  const playable = scenes.filter((s) => s.video_url !== null);
  const clips: Clip[] = playable.map((s) => ({
    id: s.id,
    url: s.video_url as string,
    durationS: 0, // real durations come from the loaded metadata
  }));
  const [state, setState] = useState<{ index: number; elapsedInClip: number } | null>(null);
  const [playing, setPlaying] = useState(false);
  const durations = useRef<Map<string, number>>(new Map());
  const videoA = useRef<HTMLVideoElement | null>(null);
  const videoB = useRef<HTMLVideoElement | null>(null);
  const raf = useRef<number | null>(null);

  const clipDurations = (): Clip[] =>
    playable.map((s) => ({
      id: s.id,
      url: s.video_url as string,
      durationS: durations.current.get(s.id) ?? s.duration_s,
    }));

  useEffect(() => {
    const tick = () => {
      setState((cur) => {
        if (!cur || !playing) return cur;
        const ds = clipDurations();
        const next = advance(ds, cur, 1 / 60);
        if (next === null) {
          setPlaying(false);
          onPlayhead?.(null);
          return cur;
        }
        const pct = (absoluteTime(ds, next) / totalDuration()) * 100;
        onPlayhead?.(pct);
        return next;
      });
      raf.current = requestAnimationFrame(tick);
    };
    if (playing) {
      raf.current = requestAnimationFrame(tick);
    }
    return () => {
      if (raf.current) cancelAnimationFrame(raf.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [playing, playable.map((s) => s.id).join(",")]);

  const totalDuration = () =>
    playable.reduce((acc, s) => acc + s.duration_s, 0);

  const current = state !== null && clips.length > 0
    ? playable[state.index] ?? null
    : null;

  const start = () => {
    durations.current.clear();
    playable.forEach((s) => {
      durations.current.set(s.id, s.duration_s);
    });
    setState(createQueue(clipDurations()));
    setPlaying(true);
  };

  const stop = () => {
    setPlaying(false);
    onPlayhead?.(null);
  };

  // keep the active <video> element in sync with the queue state
  useEffect(() => {
    const active = state?.index ?? -1;
    for (const [i, el] of [videoA.current, videoB.current].entries()) {
      if (!el) continue;
      if (i === active % 2) {
        el.src = current ? (current.video_url as string) : "";
        if (playing) void el.play().catch(() => setPlaying(false));
      } else {
        el.pause();
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state?.index, playing]);

  if (playable.length === 0) {
    return (
      <div className="player empty" data-testid="player">
        No renders yet — the stitched preview becomes available as scenes render.
      </div>
    );
  }

  return (
    <div className="player" data-testid="player">
      <div className="player-stage">
        <video ref={videoA} className={state !== null && state.index % 2 === 0 ? "active" : ""} playsInline />
        <video ref={videoB} className={state !== null && state.index % 2 === 1 ? "active" : ""} playsInline />
        {state === null && (
          <div className="player-overlay">
            <button onClick={start} title="play rendered scenes back to back">▶ Preview chain</button>
            <span className="hint">
              plays {playable.length} rendered scene{playable.length > 1 ? "s" : ""} seamlessly — nothing is stitched
            </span>
          </div>
        )}
      </div>
      {state !== null && (
        <div className="player-bar">
          <span>{current?.id}</span>
          <button onClick={() => (playing ? stop() : setPlaying(true))}>
            {playing ? "⏸" : "▶"}
          </button>
          <button onClick={() => { setState(null); stop(); }}>⏹</button>
        </div>
      )}
    </div>
  );
}
