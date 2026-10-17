"""ComfyUI-ReelStudio — node pack entry point.

Reel Studio is an app, not a node graph: it registers routes on ComfyUI's
PromptServer and serves its web UI at /reelstudio. The node mappings are a
minimal placeholder so the pack loads cleanly.
"""

NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}

WEB_DIRECTORY = "./web"

try:
    from .reelstudio.server import mount_on_prompt_server

    mount_on_prompt_server()
except ImportError:
    # Outside ComfyUI (tests, tooling) the package is imported directly.
    pass
