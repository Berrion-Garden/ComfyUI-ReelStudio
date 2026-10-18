import { useEffect, useRef, useState } from "react";
import type { SceneView } from "../types";
import { absoluteTime, advance, createQueue, type Clip } from "./queue";
import { fadeOut, sfxVolumeAt, trackPlans, type Mix } from "./mix";

export type { Mix, MixOneShot } from "./mix";

interface Props {
  scenes: SceneView[];
  onPlayhead?: (pct: number | null) => void;
  /** scrub requests: { s: absolute seconds, n: monotonically increasing } */
  seekRequest?: { s: number; n: number } | null;
  mix?: Mix | null;
}

/**
 * Plays the chain seamlessly without concatenating: two <video> elements
 * trade off — while one plays, the next scene's clip preloads in the other,
 * and the swap happens at the boundary. The reel ends only at a XXX scene.
 * Scrubbing seeks the queue to any absolute reel time.
 */
export function Player({ scenes, onPlayhead, seekRequest, mix }: Props) {
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
  const lastTick = useRef<number | null>(null);

  const clipDurations = (): Clip[] =>
    playable.map((s) => ({
      id: s.id,
      url: s.video_url as string,
      durationS: durations.current.get(s.id) ?? s.duration_s,
    }));

  useEffect(() => {
    if (!playing) {
      lastTick.current = null;
      return;
    }
    // wall-clock delta, not a fixed 1/60 per rAF frame — rAF fires at the
    // display's refresh rate, which double-speeds the reel on 120 Hz+ screens
    lastTick.current = performance.now();
    const tick = () => {
      const now = performance.now();
      const dt = Math.min((now - (lastTick.current ?? now)) / 1000, 0.25);
      lastTick.current = now;
      setState((cur) => {
        if (!cur || !playing) return cur;
        const ds = clipDurations();
        const next = advance(ds, cur, dt);
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
    raf.current = requestAnimationFrame(tick);
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

  // scrub: jump the queue to the requested absolute time
  useEffect(() => {
    if (!seekRequest || playable.length === 0) return;
    durations.current.clear();
    playable.forEach((s) => durations.current.set(s.id, s.duration_s));
    setState(createQueue(clipDurations(), seekRequest.s));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [seekRequest?.n]);

  // keep the active <video> element in sync with the queue state.
  // Runs on index change, play/pause, or an explicit seek — NOT on every
  // elapsed-frame update (elapsedInClip ticks at rAF rate; reassigning src
  // and currentTime that often would reset playback).
  const stateRef = useRef(state);
  stateRef.current = state;
  const applied = useRef<{ index: number; seek: number }>({ index: -1, seek: -1 });
  useEffect(() => {
    const cur = stateRef.current;
    const active = cur?.index ?? -1;
    const seekN = seekRequest?.n ?? -1;
    const fresh = applied.current.index !== active || applied.current.seek !== seekN;
    for (const [i, el] of [videoA.current, videoB.current].entries()) {
      if (!el) continue;
      if (i === active % 2) {
        const url = current ? (current.video_url as string) : "";
        if (el.getAttribute("src") !== url) el.src = url;
        if (fresh && cur) {
          el.currentTime = Math.min(cur.elapsedInClip, el.duration || Infinity);
        }
        // both branches matter: leaving the active element un-paused on
        // pause kept its baked audio rolling "in the background"
        if (playing) void el.play().catch(() => setPlaying(false));
        else el.pause();
      } else {
        el.pause();
      }
    }
    applied.current = { index: active, seek: seekN };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state?.index, playing, seekRequest?.n, current?.id]);

  // ------------------------------------------------------------ the mix --
  // On-the-fly layering of everything the yaml drives: audio tracks (at
  // seek, under their volume envelopes), placed one-shots from the sfx
  // board, and the sfx envelope on the baked clip audio — resynced on
  // play/pause/seek.
  const trackEls = useRef<Map<string, HTMLAudioElement>>(new Map());
  const shotEls = useRef<Map<string, HTMLAudioElement>>(new Map());
  const shotsFired = useRef<Set<string>>(new Set());
  const resync = useRef(true);
  const mixRef = useRef(mix);
  mixRef.current = mix;

  const pauseMix = () => {
    for (const el of trackEls.current.values()) el.pause();
    for (const el of shotEls.current.values()) el.pause();
  };

  const applyMix = (t: number) => {
    const m = mixRef.current;
    if (!m) return;
    const masterVideo = (stateRef.current?.index ?? 0) % 2 === 0
      ? videoA.current : videoB.current;
    if (masterVideo) {
      masterVideo.volume = sfxVolumeAt(m.sfxVolume, t, m.totalS, m.useMusic);
    }
    for (const plan of trackPlans(m.sources, t, m.totalS)) {
      const el = trackEls.current.get(plan.key);
      if (!el || el.getAttribute("src") == null) continue;
      if (plan.active) {
        if (resync.current || Math.abs(el.currentTime - plan.offset) > 0.25) {
          el.currentTime = plan.offset;
        }
        el.volume = plan.volume;
        if (el.paused) void el.play().catch(() => { /* autoplay-guarded */ });
      } else if (!el.paused) {
        el.pause();
      }
    }
    for (const shot of m.oneShots) {
      if (shotsFired.current.has(shot.key)
        || t < shot.atS || t >= shot.atS + 0.3) continue;
      const el = shotEls.current.get(shot.key);
      if (!el || !el.getAttribute("src")) continue;
      shotsFired.current.add(shot.key);
      el.currentTime = 0;
      el.volume = shot.gain * fadeOut(t, m.totalS);
      void el.play().catch(() => { /* autoplay-guarded */ });
    }
    resync.current = false;
  };

  useEffect(() => {
    if (!playing || state === null) return;
    applyMix(absoluteTime(clipDurations(), state));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state?.index, state?.elapsedInClip, playing]);

  useEffect(() => {
    if (!playing) pauseMix();           // pause/stop/asset-view silences the mix
    if (seekRequest) shotsFired.current.clear();  // seeking back may re-fire
    resync.current = true;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [playing, seekRequest?.n]);

  // the OS media controls (macOS Now Playing etc.) grab whichever element is
  // audible — route their play/pause to the WHOLE preview, not one element
  useEffect(() => {
    if (!("mediaSession" in navigator)) return;
    try {
      navigator.mediaSession.setActionHandler("pause", () => setPlaying(false));
      navigator.mediaSession.setActionHandler("play", () => setPlaying(true));
    } catch { /* unsupported actions on some platforms */ }
    return () => {
      try {
        navigator.mediaSession.setActionHandler("pause", null);
        navigator.mediaSession.setActionHandler("play", null);
      } catch { /* ignore */ }
    };
  }, []);

  if (playable.length === 0) {
    return (
      <div className="player empty" data-testid="player">
        No renders yet — the stitched preview becomes available as scenes render.
      </div>
    );
  }

  return (
    <div className="player" data-testid="player">
      {mix && mix.sources.map((s) => (
        <audio key={s.key} ref={(el) => { if (el) trackEls.current.set(s.key, el); }}
          src={s.url} preload="auto" />
      ))}
      {mix && mix.oneShots.map((s) => (
        <audio key={s.key} ref={(el) => { if (el) shotEls.current.set(s.key, el); }}
          src={s.url} preload="auto" />
      ))}
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
