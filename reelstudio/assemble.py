"""Assembly: music bed, synth bell, clip concat, final mix.

The only step that concatenates. Everything before it (playback included)
treats scenes as individual clips.
"""

import glob
import re
import subprocess
from pathlib import Path

import numpy as np

from .project import Project
from .timeline import SECONDS_DIGITS, scene_starts, total_dur

FFMPEG = "/usr/bin/ffmpeg"
SR = 32000


def music_segments(project: Project) -> list[dict]:
    """Scene-anchored segments: start at their scene, run to the next anchor
    (or reel end). Each carries a hash for staleness tracking."""
    import hashlib

    starts = scene_starts(project)
    total = total_dur(project)
    anchors = [(i, s["music"]) for i, s in enumerate(project.scenes)
               if isinstance(s.get("music"), dict)]
    out = []
    for k, (idx, m) in enumerate(anchors):
        start = starts[idx]
        end = starts[anchors[k + 1][0]] if k + 1 < len(anchors) else total
        seg = {
            "name": m["name"],
            "caption": m["caption"].format(**project.aliases),
            "start": round(start, SECONDS_DIGITS),
            "dur": round(end - start, SECONDS_DIGITS),
            "gain": m.get("gain", 1.0),
        }
        blob = f"{seg['caption']}|{seg['start']}|{seg['dur']}|{seg['gain']}"
        seg["hash"] = hashlib.sha256(blob.encode()).hexdigest()[:16]
        out.append(seg)
    return out


def music_overlays(project: Project) -> list[dict]:
    """Real audio-file overlays (`music_2`) — the tracks the production mix
    actually uses. Each starts at its scene (+ optional `at`) and runs until
    the last `fades` keyframe (or the reel end). `seek`/`gain` ride along for
    display and future mixing."""
    starts = scene_starts(project)
    total = total_dur(project)
    out = []
    for i, s in enumerate(project.scenes):
        for m in s.get("music_2") or []:
            start = starts[i] + float(m.get("at", 0.0))
            fades = m.get("fades") or []
            end = float(fades[-1][0]) if fades else total
            name = re.sub(r"^\d+\s+-\s+", "", Path(m["file"]).stem)
            out.append({
                "name": name,
                "file": m["file"],
                "start": round(start, SECONDS_DIGITS),
                "dur": round(end - start, SECONDS_DIGITS),
                "gain": m.get("gain", 1.0),
                "seek": m.get("seek", 0.0),
            })
    return out


def bell_wav(n: int, sr: int) -> np.ndarray:
    """3 bright chime strikes, Japanese-school-bell flavor."""
    t = np.arange(n) / sr
    out = np.zeros((n, 2), dtype=np.float32)
    for strike in (0.0, 0.55, 1.1):
        i0 = int(strike * sr)
        if i0 >= n:
            continue
        tt = t[:n - i0]
        tone = np.zeros(n - i0, dtype=np.float32)
        for f, amp, dec in ((2093, 1.0, 0.9), (2637, 0.55, 0.7),
                            (3136, 0.4, 0.5), (1046, 0.35, 1.3)):
            tone += amp * np.sin(2 * np.pi * f * tt) * np.exp(-tt / dec)
        tone *= np.minimum(1.0, tt * 200)
        out[i0:, 0] += tone * 0.9
        out[i0:, 1] += tone * 0.75
    return out


def load_audio(path: str | Path, sr: int = SR) -> np.ndarray:
    raw = subprocess.run(
        [FFMPEG, "-v", "error", "-i", str(path), "-f", "f32le",
         "-acodec", "pcm_f32le", "-ac", "2", "-ar", str(sr), "-"],
        capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32).reshape(-1, 2)


def _music_bed(project: Project, use_music: bool) -> np.ndarray:
    total = total_dur(project)
    n_total = int(round(total * SR)) + SR
    bed = np.zeros((n_total, 2), dtype=np.float32)
    if not use_music:
        return bed
    reel_dir = project.meta["reel_dir"]
    for m in music_segments(project):
        hits = [p for p in glob.glob(f"{reel_dir}/music_{m['name']}_*")
                if not p.endswith(("json", "log"))]
        if not hits:
            raise FileNotFoundError(f"no audio for music segment {m['name']!r}")
        a = load_audio(sorted(hits)[-1])[:int(round(m["dur"] * SR))]
        if a.shape[0] < int(round(m["dur"] * SR)):
            pad = np.zeros((int(round(m["dur"] * SR)) - a.shape[0], 2),
                           dtype=np.float32)
            hold = int(min(0.5 * SR, a.shape[0]))
            if hold:
                pad[:hold] = a[-1:]
            a = np.vstack([a, pad])
        a = a * m["gain"]
        f = int(0.08 * SR)  # 80 ms equal-power fade at segment ends (no clicks)
        env = np.ones((a.shape[0], 1), dtype=np.float32)
        env[:f, 0] = np.linspace(0, 1, f)
        env[-f:, 0] = np.linspace(1, 0, f)
        i0 = int(round(m["start"] * SR))
        bed[i0:i0 + a.shape[0]] += a * env
    return bed


def assemble(project: Project, out_path: str, use_music: bool,
             work_dir: str = "/tmp/opencode") -> str:
    """Concat scene deliverables, mix the bed + bell, fade out, write final.
    Returns out_path."""
    meta = project.meta
    scenes = project.scenes
    starts = scene_starts(project)
    total = total_dur(project)

    bed = _music_bed(project, use_music)

    # synth bell at every scene with sound_effects.bell (bell_at = scene offset)
    for i, s in enumerate(scenes):
        se = s.get("sound_effects", {})
        if se.get("bell"):
            bi = int(round((starts[i] + se.get("bell_at", 0)) * SR))
            bed[bi:] += bell_wav(bed.shape[0] - bi, SR) * 0.5

    fo = int(1.2 * SR)  # gentle fade-out over the final 1.2 s
    bed[-fo:] *= np.linspace(1, 0, fo)[:, None]
    peak = np.abs(bed).max()
    if peak > 0.85:
        bed *= 0.85 / peak
    bed_path = Path(work_dir) / "bed.wav"
    bed_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([FFMPEG, "-y", "-v", "error", "-f", "f32le", "-ar", str(SR),
                    "-ac", "2", "-i", "-", "-c:a", "pcm_s16le", str(bed_path)],
                   input=bed.astype(np.float32).tobytes(), check=True)

    from .manifest import deliverable

    inputs = []
    for s in scenes:
        d = deliverable(meta["reel_dir"], s["id"])
        if d is None:
            raise FileNotFoundError(f"scene {s['id']} has no render — cannot assemble")
        inputs += ["-i", d]
    n = len(scenes)
    # effects ride at full level when there's no music bed carrying them
    sfx_gain = "0.45" if use_music else "1.0"
    filters = [f"[{i}:a]volume={sfx_gain},aresample={SR}[a{i}]" for i in range(n)]
    filters.append("".join(f"[{i}:v]" for i in range(n))
                   + f"concat=n={n}:v=1:a=0[vcat]")
    filters.append(f"[vcat]fade=t=out:st={total - 1.2:.2f}:d=1.2[vf]")
    filters.append("".join(f"[a{i}]" for i in range(n))
                   + f"concat=n={n}:v=0:a=1[acat]")
    filters.append(f"[{n}:a]aresample={SR}[bed]")
    filters.append("[acat][bed]amix=inputs=2:normalize=0:duration=first[aout]")
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([FFMPEG, "-v", "error", "-y", *inputs, "-i", str(bed_path),
                    "-filter_complex", ";".join(filters), "-map", "[vf]",
                    "-map", "[aout]", "-c:v", "libx264", "-crf", "17",
                    "-preset", "medium", "-pix_fmt", "yuv420p", "-c:a", "aac",
                    "-b:a", "192k", "-shortest", str(out_path)], check=True)
    return out_path
