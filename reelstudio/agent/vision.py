"""Images into the agent's eyes.

The gateway carries pictures in USER messages only — a tool message with an
image part is rejected ("cannot be flattened"). So both paths deliver through
user turns: the operator's primary selection rides their message, and the
view_image tool's result is followed by a user turn holding the picture.
"""

import base64
from pathlib import Path

from ..assets import asset_file
from ..errors import ValidationError

IMAGE_EXTS = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
              ".webp": "image/webp", ".gif": "image/gif"}
MAX_BYTES = 6 * 1024 * 1024


def data_url(path: str, roots) -> tuple[str, str]:
    """One (label, data-url) pair for an image inside the asset roots."""
    p = asset_file(str(path), roots)
    mime = IMAGE_EXTS.get(p.suffix.lower())
    if mime is None:
        raise ValidationError(
            [f"{p.name} is not a viewable image",
             f"viewable: {sorted(IMAGE_EXTS)}"])
    data = p.read_bytes()
    if len(data) > MAX_BYTES:
        raise ValidationError([f"{p.name} exceeds the 6MB view cap"])
    return p.name, f"data:{mime};base64," + base64.b64encode(data).decode()


def content_parts(text: str, images: list[tuple[str, str]]) -> dict | str:
    """A user message: plain text when there are no images, else a content
    array — the text, then each image with its label beside it."""
    if not images:
        return {"role": "user", "content": text}
    parts: list[dict] = [{"type": "text", "text": text}] if text else []
    for label, url in images:
        parts += [{"type": "text", "text": f"[image: {label}]"},
                  {"type": "image_url", "image_url": {"url": url}}]
    return {"role": "user", "content": parts}
