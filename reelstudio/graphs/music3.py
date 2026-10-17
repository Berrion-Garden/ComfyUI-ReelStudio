"""Music 3 segment graph: one captioned, scene-anchored bed segment."""


def build_music_graph(caption: str, seed: int, duration_s: float,
                      output_prefix: str) -> dict:
    """MiniMax Music 3: 30 steps / cfg 1.7 / euler-simple; latent runs 2 s
    long so the segment always covers its span, trimmed at mix time."""
    dur = duration_s + 2.0
    g = {
        "1": {"class_type": "UNETLoader", "inputs": {
            "unet_name": "minimax_music3_dit_fp16.safetensors",
            "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader", "inputs": {
            "clip_name": "minimax_music3_text_encoder_pruned_int8_convrot.safetensors",
            "type": "minimax", "device": "default"}},
        "3": {"class_type": "VAELoader", "inputs": {
            "vae_name": "minimax_music3_dav.safetensors"}},
        "4": {"class_type": "MiniMaxMusic3TextEncode", "inputs": {
            "clip": ["2", 0], "caption": caption, "lyrics": "",
            "seed": seed, "max_duration": dur, "cfg_scale": 1.7, "top_k": 50}},
        "5": {"class_type": "ConditioningZeroOut", "inputs": {
            "conditioning": ["4", 0]}},
        "6": {"class_type": "EmptyMiniMaxMusic3LatentAudio", "inputs": {
            "seconds": dur, "batch_size": 1}},
        "7": {"class_type": "KSampler", "inputs": {
            "model": ["1", 0], "positive": ["4", 0], "negative": ["5", 0],
            "latent_image": ["6", 0],
            "seed": seed, "steps": 30, "cfg": 1.7, "sampler_name": "euler",
            "scheduler": "simple", "denoise": 1.0}},
        "8": {"class_type": "VAEDecodeAudio", "inputs": {
            "samples": ["7", 0], "vae": ["3", 0]}},
        "9": {"class_type": "SaveAudio", "inputs": {
            "audio": ["8", 0], "filename_prefix": output_prefix}},
    }
    return g
