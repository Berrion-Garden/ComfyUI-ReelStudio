"""Graph builders. Pure functions: graph in, API-format dict out — no I/O,
so they can be golden-tested without a server.

H3 gotchas carried over from the serving work:
- clip lengths are 17n+5
- SaveVideo needs format 'auto' in API graphs
- flow matching: no negative conditioning node — the negative rides in the
  prompt text (h3_prompt), never in the graph
- weight paths are bare filenames, never subdirectory-prefixed
"""

import random

# Loader block shared by every MiniMax render (video + music).
LOADERS = {
    "1": {"class_type": "UNETLoader", "inputs": {
        "unet_name": "minimax_h3_fl2va_pruned_int8_convrot.safetensors",
        "weight_dtype": "default"}},
    "2": {"class_type": "CLIPLoader", "inputs": {
        "clip_name": "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors",
        "type": "minimax", "device": "default"}},
    "3": {"class_type": "VAELoader", "inputs": {
        "vae_name": "minimax_h3_video_vae_fp16.safetensors"}},
    "4": {"class_type": "VAELoader", "inputs": {
        "vae_name": "minimax_h3_audio_vae_fp32.safetensors"}},
}


def h3_prompt(video: dict, sound_effects: dict | None, aliases: dict) -> str:
    """description + soundscape + music disclaimer + negative -> one prompt.
    H3 bakes the soundscape into the clip; music is banned here and lives in
    the assemble step."""
    desc = (video.get("description") or "").format(**aliases).rstrip()
    sfx = ((sound_effects or {}).get("soundscape") or "").format(**aliases)
    parts = [
        desc,
        f"overall_soundscape: {sfx}",
        "non_diegetic_music: None. There is absolutely NO music in this scene: "
        "no instruments, no electric guitar, no riffs, no drums, no score, no "
        "jingle — only the natural diegetic sounds described in the soundscape.",
    ]
    negative = video.get("negative")
    if negative:
        parts.append(f"negative_prompt: {negative.strip().format(**aliases)}")
    return "\n\n".join(parts) + "\n"


def build_h3_graph(prompt: str, seed: int, width: int, height: int, steps: int,
                   frames: int, fps: float, output_prefix: str,
                   first_image: str | None, last_image: str | None) -> dict:
    """MiniMaxH3ImageToVideo + custom sampling chain -> SaveVideo.
    Frames pass through as-is: H3 rendered off-grid lengths (45, 80) fine in
    practice — the 17n+5 grid is surfaced as a validation warning, not a block."""
    if frames <= 0:
        raise ValueError(f"frames must be positive, got {frames}")

    g = {
        **{k: {"class_type": v["class_type"], "inputs": dict(v["inputs"])}
           for k, v in LOADERS.items()},
        "5": {"class_type": "MiniMaxH3ImageToVideo", "inputs": {
            "clip": ["2", 0], "vae": ["3", 0], "prompt": prompt,
            "width": width, "height": height, "length": frames}},
        "6": {"class_type": "KSamplerSelect", "inputs": {
            "sampler_name": "res_multistep"}},
        "7": {"class_type": "BasicScheduler", "inputs": {
            "model": ["1", 0], "scheduler": "simple", "steps": steps,
            "denoise": 1.0}},
        "8": {"class_type": "BasicGuider", "inputs": {
            "model": ["1", 0], "conditioning": ["5", 0]}},
        "9": {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}},
        "10": {"class_type": "SamplerCustomAdvanced", "inputs": {
            "noise": ["9", 0], "guider": ["8", 0], "sampler": ["6", 0],
            "sigmas": ["7", 0], "latent_image": ["5", 1]}},
        "11": {"class_type": "VAEDecode", "inputs": {
            "samples": ["10", 0], "vae": ["3", 0]}},
        "12": {"class_type": "VAEDecodeAudio", "inputs": {
            "samples": ["10", 0], "vae": ["4", 0]}},
        "13": {"class_type": "CreateVideo", "inputs": {
            "images": ["11", 0], "fps": float(fps), "audio": ["12", 0]}},
        "14": {"class_type": "SaveVideo", "inputs": {
            "video": ["13", 0], "filename_prefix": output_prefix,
            "format": "auto"}},
    }
    if first_image:
        g["20"] = {"class_type": "LoadImage", "inputs": {"image": first_image}}
        g["5"]["inputs"]["first_frame"] = ["20", 0]
    if last_image:
        g["21"] = {"class_type": "LoadImage", "inputs": {"image": last_image}}
        g["5"]["inputs"]["last_frame"] = ["21", 0]
    return g


def new_seed() -> int:
    return random.SystemRandom().getrandbits(60)
