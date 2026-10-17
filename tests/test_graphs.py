"""Graph builders are pure: golden dict, prompt assembly, grid passthrough."""

from reelstudio.graphs import h3_video, music3

VIDEO = {"mode": "i2v", "first": "prev_last", "last": None,
         "description": "The fox eats noodles. {fox}.",
         "negative": "text, watermark"}
SFX = {"soundscape": "slurp"}
ALIASES = {"fox": "the pink fox boy"}


def test_golden_h3_graph():
    g = h3_video.build_h3_graph(
        prompt="p", seed=42, width=768, height=768, steps=20, frames=107,
        fps=24, output_prefix="anime_fantasy/h3_reel/s1",
        first_image=None, last_image=None)
    assert g["5"]["class_type"] == "MiniMaxH3ImageToVideo"
    assert g["5"]["inputs"]["length"] == 107
    assert g["14"]["class_type"] == "SaveVideo"
    assert g["14"]["inputs"]["format"] == "auto"          # H3 requirement
    assert g["9"]["inputs"]["noise_seed"] == 42
    # flow matching: NO negative conditioning node — negatives ride in prompt
    assert "ConditioningZeroOut" not in {n["class_type"] for n in g.values()}
    assert g["14"]["inputs"]["filename_prefix"] == "anime_fantasy/h3_reel/s1"


def test_anchor_images_attach_loadimage_nodes():
    g = h3_video.build_h3_graph(
        prompt="p", seed=1, width=768, height=768, steps=20, frames=107,
        fps=24, output_prefix="x", first_image="a.png", last_image="b.png")
    assert g["5"]["inputs"]["first_frame"] == ["20", 0]
    assert g["5"]["inputs"]["last_frame"] == ["21", 0]
    assert g["20"]["inputs"]["image"] == "a.png"


def test_off_grid_frames_pass_through():
    # the real reel generated 45- and 80-frame scenes successfully
    g = h3_video.build_h3_graph(prompt="p", seed=1, width=768, height=768,
                                steps=20, frames=80, fps=24, output_prefix="x",
                                first_image=None, last_image=None)
    assert g["5"]["inputs"]["length"] == 80


def test_prompt_assembles_layers_and_resolves_aliases():
    p = h3_video.h3_prompt(VIDEO, SFX, ALIASES)
    assert "the pink fox boy" in p
    assert "overall_soundscape: slurp" in p
    assert "negative_prompt: text, watermark" in p
    assert "absolutely NO music" in p


def test_music_graph_shape():
    g = music3.build_music_graph(caption="rock", seed=7, duration_s=10.0,
                                 output_prefix="pre")
    assert g["4"]["inputs"]["max_duration"] == 12.0      # dur + 2 s
    assert g["6"]["inputs"]["seconds"] == 12.0
    assert g["7"]["inputs"]["seed"] == g["4"]["inputs"]["seed"] == 7
    assert g["9"]["inputs"]["filename_prefix"] == "pre"
