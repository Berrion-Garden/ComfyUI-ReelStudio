"""Rendering: scene clips (H3), freeze post, music segments.

Renders never cut frames: scene length is generated (frames on the H3 grid),
and the prev_last junction stays frame-exact because each scene starts on the
upstream deliverable's actual last frame.
"""

import glob
import os
import subprocess
from pathlib import Path

from .comfy_client import ComfyClient
from .graphs import h3_video, music3
from . import manifest as manifest_mod
from .manifest import deliverable as find_deliverable
from .manifest import record_music, record_scene
from .project import Project, file_hash
from .timeline import chain_hash, config_hash, scene_frames

FFMPEG = "/usr/bin/ffmpeg"


def _freeze_post(scene: dict, meta: dict, reel_dir: str, work_dir: str) -> str:
    """motion -> white impact flash -> graded slow-push-in freeze, muxed with
    the raw clip audio + a synth 'ching' at the freeze point. Ported from the
    anime_reel pipeline (ffmpeg command for command)."""
    fr = scene["post"]["freeze"]
    sid = scene["id"]
    # source = newest RENDER only; drop stale freeze outputs so neither the
    # source glob nor the output path can see them
    for old in glob.glob(f"{reel_dir}/{sid}_9_freeze_*"):
        os.remove(old)
    src = sorted(p for p in glob.glob(f"{reel_dir}/{sid}_*.mp4")
                 if "_9_freeze_" not in p)[-1]
    raw = f"{work_dir}/{sid}_freeze_raw.png"
    subprocess.run([FFMPEG, "-y", "-v", "error", "-sseof", "-0.05", "-i", src,
                    "-frames:v", "1", raw], check=True)
    g = fr["grade"]
    vf = (f"eq=saturation={g['saturation']}:contrast={g['contrast']}:"
          f"brightness={g.get('brightness', 0)},unsharp=5:5:1.2")
    if g.get("vignette"):
        vf += ",vignette=PI/4.2"
    graded = f"{work_dir}/{sid}_freeze_graded.png"
    subprocess.run([FFMPEG, "-y", "-v", "error", "-i", raw, "-vf", vf,
                    "-frames:v", "1", graded], check=True)

    fps = meta["fps"]
    motion_s = fr["at_s"]
    flash_s = fr.get("flash_s", 0.125)
    frames = scene.get("frames", meta["frames"])
    freeze_s = round(frames / fps - motion_s - flash_s, 4)
    parts = []
    for kind, arg in [("motion", f"-i {src} -t {motion_s}"),
                      ("flash", f"-f lavfi -i color=white:s={meta['width']}x{meta['height']}:d={flash_s}:r={fps}")]:
        out = f"{work_dir}/{sid}_part_{kind}.mp4"
        subprocess.run([FFMPEG, "-y", "-v", "error", *arg.split(), "-an",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "16",
                        out], check=True)
        parts.append(out)

    out = f"{work_dir}/{sid}_part_freeze.mp4"
    zoom = ("zoompan=z=1+0.0022*on:d=1:x=iw/2-(iw/zoom/2):y=ih/2-(ih/zoom/2):"
            f"s={meta['width']}x{meta['height']}:fps={fps}")
    names = fr.get("names")
    if names:
        vf = f"fps={fps}," + ",".join(_name_drawtext(names, meta, 0.45)) + "," + zoom
        subprocess.run([FFMPEG, "-y", "-v", "error", "-loop", "1", "-i", graded,
                        "-vf", vf, "-t", str(freeze_s), "-an", "-c:v", "libx264",
                        "-pix_fmt", "yuv420p", "-crf", "16", out], check=True)
    else:
        subprocess.run([FFMPEG, "-y", "-v", "error", "-loop", "1", "-i", graded,
                        "-vf", zoom, "-t", str(freeze_s), "-an", "-c:v", "libx264",
                        "-pix_fmt", "yuv420p", "-crf", "16", out], check=True)
    parts.append(out)

    joined = f"{work_dir}/{sid}_freeze_video.mp4"
    subprocess.run([FFMPEG, "-y", "-v", "error", "-i", parts[0], "-i", parts[1],
                    "-i", parts[2], "-filter_complex",
                    "[0:v][1:v][2:v]concat=n=3:v=1:a=0[v]", "-map", "[v]",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "16",
                    joined], check=True)
    out_path = f"{reel_dir}/{sid}_9_freeze_.mp4"
    ms = int(fr["at_s"] * 1000)
    subprocess.run([FFMPEG, "-y", "-v", "error", "-i", joined, "-i", src,
                    "-f", "lavfi", "-i", "sine=frequency=170:duration=0.35",
                    "-f", "lavfi", "-i", "sine=frequency=2093:duration=0.22",
                    "-f", "lavfi", "-i", "sine=frequency=3520:duration=0.18",
                    "-f", "lavfi", "-i", "anoisesrc=d=0.09:c=pink:a=0.5",
                    "-filter_complex",
                    "[2:a]afade=t=out:st=0.04:d=0.3,volume=2.2,aresample=44100[t];"
                    "[3:a]afade=t=out:st=0.005:d=0.2,volume=0.7,aresample=44100[c1];"
                    "[4:a]afade=t=out:st=0.005:d=0.16,volume=0.5,aresample=44100[c2];"
                    "[5:a]afade=t=out:st=0.015:d=0.075,volume=1.2,aresample=44100[n];"
                    "[t][c1][c2][n]amix=inputs=4:duration=longest:normalize=0,"
                    f"adelay={ms}:all=1[pop];"
                    "[1:a]aresample=44100[base];"
                    "[base][pop]amix=inputs=2:duration=first:normalize=0[a]",
                    "-map", "0:v", "-map", "[a]", "-c:v", "libx264",
                    "-crf", "16", "-pix_fmt", "yuv420p", "-c:a", "aac",
                    "-b:a", "192k", "-shortest", out_path], check=True)
    return out_path


def _name_drawtext(names_cfg: dict, meta: dict, slide_s: float) -> list[str]:
    """drawtext chain: each name line slides in from its side (ease-out)."""
    font = "/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc"
    W = meta["width"]
    ease = f"pow(1-min(t/{slide_s},1),3)"
    vf = []
    for side in names_cfg.values():
        color = side["color"]
        if isinstance(color, int):  # yaml reads 0xFF5FA8 as a number
            color = f"0x{color:06X}"
        y = side.get("y", 60)
        for line in side["lines"]:
            xf = (f"w-text_w-24+{W}*{ease}" if side["x"] == "right"
                  else f"{side['x']}-{W}*{ease}")
            vf.append(f"drawtext=fontfile={font}:text='{line}':fontcolor={color}"
                      f":fontsize=36:x='{xf}':y={y}:borderw=4:bordercolor=black")
            y += 44
    return vf


# ---------------------------------------------------------------- render ---

def resolve_anchor_file(project: Project, scene: dict, which: str,
                        work_dir: str, client: ComfyClient) -> Path | None:
    """first/last anchor ref -> a real file path, extracting prev_last from
    the upstream deliverable's actual last frame."""
    ref = scene["video"].get(which)
    if ref in (None, "", "null"):
        return None
    if ref == "prev_last":
        prev = project.previous(scene["id"])
        if prev is None:
            raise ValueError(f"{scene['id']}: prev_last with no previous scene")
        prev_clip = find_deliverable(project.meta["reel_dir"], prev["id"])
        if prev_clip is None:
            raise FileNotFoundError(
                f"{scene['id']}: upstream {prev['id']} has no render — "
                "render it first (prev_last junction)")
        out = Path(work_dir) / f"{scene['id']}_{which}.png"
        return client.extract_last_frame(prev_clip, out)
    if ref.startswith("still:"):
        return project.still_path(ref.split(":", 1)[1])
    return Path(ref)


def render_scene(project: Project, scene_id: str, client: ComfyClient,
                 work_dir: str, seed: int | None = None) -> str:
    """Render one scene through Comfy, apply freeze post, update the manifest.
    Returns the deliverable path."""
    scene = project.scene(scene_id)
    if scene is None:
        raise KeyError(scene_id)
    meta = project.meta
    reel_dir = meta["reel_dir"]
    Path(reel_dir).mkdir(parents=True, exist_ok=True)
    Path(work_dir).mkdir(parents=True, exist_ok=True)

    first = resolve_anchor_file(project, scene, "first", work_dir, client)
    last = resolve_anchor_file(project, scene, "last", work_dir, client)
    staged_first = client.stage_input(f"{scene_id}_first.png", first) if first else None
    staged_last = client.stage_input(f"{scene_id}_last.png", last) if last else None

    prefix = _output_prefix(project)
    prompt = h3_video.h3_prompt(scene["video"], scene.get("sound_effects"),
                                project.aliases)
    graph = h3_video.build_h3_graph(
        prompt=prompt,
        seed=seed if seed is not None else h3_video.new_seed(),
        width=meta["width"], height=meta["height"], steps=meta.get("steps", 20),
        frames=scene_frames(project, scene), fps=meta["fps"],
        output_prefix=f"{prefix}/{scene_id}",
        first_image=staged_first, last_image=staged_last)
    rec = client.submit_wait(graph)
    _sync_outputs(client, project, rec)

    deliverable_path = find_deliverable(reel_dir, scene_id)
    if deliverable_path is None:
        raise FileNotFoundError(f"{scene_id}: Comfy reported success but no render landed in {reel_dir}")

    if scene.get("post", {}).get("freeze"):
        deliverable_path = _freeze_post(scene, meta, reel_dir, work_dir)

    upstream = None
    if scene["video"].get("first") == "prev_last":
        prev = project.previous(scene_id)
        prev_entry = manifest_mod.load(reel_dir)["scenes"].get(prev["id"], {})
        prev_file = (prev_entry.get("video") or {}).get("path", {}).get("file")
        if prev_file:
            upstream = (prev["id"], prev_file)

    record_scene(reel_dir, scene_id, chain_hash(project, scene),
                 deliverable_path, scene_frames(project, scene),
                 prompt_id=_prompt_id(rec), upstream=upstream)
    return deliverable_path


def _prompt_id(history_rec: dict) -> str:
    prompt = history_rec.get("prompt")
    return prompt.get("prompt_id", "") if isinstance(prompt, dict) else ""


def render_music(project: Project, name: str, client: ComfyClient,
                 seed: int | None = None) -> str:
    """(Re)generate one anchored music segment by name."""
    from .assemble import music_segments

    segment = next((m for m in music_segments(project) if m["name"] == name), None)
    if segment is None:
        raise KeyError(f"no music segment named {name!r}")
    meta = project.meta
    reel_dir = meta["reel_dir"]
    prefix = _output_prefix(project)
    graph = music3.build_music_graph(
        caption=segment["caption"],
        seed=seed if seed is not None else h3_video.new_seed(),
        duration_s=segment["dur"],
        output_prefix=f"{prefix}/music_{name}")
    rec = client.submit_wait(graph)
    _sync_outputs(client, project, rec)
    hits = [p for p in glob.glob(f"{reel_dir}/music_{name}_*")
            if not p.endswith(("json", "log"))]
    audio_path = sorted(hits)[-1]
    record_music(reel_dir, name, segment["hash"], audio_path)
    return audio_path


def _output_prefix(project: Project) -> str:
    """reel_dir lives under ComfyUI's output dir; the graph prefix is relative
    to it. Take the suffix after .../output/ when recognizable."""
    reel_dir = str(Path(project.meta["reel_dir"]).resolve())
    marker = f"{os.sep}output{os.sep}"
    return reel_dir.split(marker, 1)[1] if marker in reel_dir else reel_dir


def _sync_outputs(client: ComfyClient, project: Project, rec: dict) -> None:
    """No-op on the standard layout: Comfy writes into its own output dir and
    reel_dir points inside it. Overridden in tests where the fake server
    writes elsewhere."""
