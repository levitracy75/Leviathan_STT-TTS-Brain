"""
Overlay renderer for speech/thought bubbles.
Generates a transparent PNG you can add as an image source in Streamlabs/OBS.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Tuple

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

DEFAULT_SIZE = (1000, 260)
DEFAULT_FONT_CACHE: Dict[int, ImageFont.FreeTypeFont | ImageFont.ImageFont] = {}
DEFAULT_FONT_SIZE = 30


@dataclass
class OverlayTheme:
    background: Tuple[int, int, int, int]
    border: Tuple[int, int, int, int]
    text: Tuple[int, int, int, int]


SPEAK_THEME = OverlayTheme(
    background=(255, 255, 255, 235),  # white bubble
    border=(20, 20, 20, 235),         # dark outline
    text=(20, 20, 20, 255),           # black text
)

THINK_THEME = OverlayTheme(
    background=(255, 255, 255, 235),  # white
    border=(20, 20, 20, 235),         # dark outline
    text=(20, 20, 20, 255),
)


def render_overlay(
    text: str,
    output_path: str | Path,
    mode: str = "speak",
    font_size: int = DEFAULT_FONT_SIZE,
    size: Tuple[int, int] = DEFAULT_SIZE,
) -> Path:
    """
    Render a bubble overlay with the given text and save to output_path.
    mode: "speak" or "think" (chooses colors/shapes).
    """
    cleaned = _clean_text(text)
    if not cleaned:
        return render_empty_overlay(output_path, size=size)

    theme = SPEAK_THEME if mode == "speak" else THINK_THEME
    width, height = size
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    font = _get_font(font_size)

    # Bubble body
    padding = 24
    if mode == "think":
        # Compact pill near center-top for thinking
        pill_width = int(width * 0.7)
        pill_height = int(height * 0.45)
        left = (width - pill_width) // 2
        right = left + pill_width
        top = padding
        bottom = top + pill_height
        rect = [left, top, right, bottom]
        radius = pill_height // 2
    else:
        rect = [padding, padding, width - padding, height - padding - 48]
        radius = 32

    draw.rounded_rectangle(rect, radius=radius, fill=theme.background, outline=theme.border, width=4)

    # Tail / bubbles
    if mode == "speak":
        mid_x = width // 2
        tail = [
            (mid_x - 40, height - 60),
            (mid_x + 40, height - 60),
            (mid_x, height - 10),
        ]
        draw.polygon(tail, fill=theme.background, outline=theme.border)
    else:
        # Three small dots centered below the pill
        center_x = width // 2
        base_y = rect[3] + 10
        bubble_sizes = [20, 26, 32]
        offsets = [0, 26, 56]
        for size, offset in zip(bubble_sizes, offsets):
            r = size
            cx = center_x - r // 2
            cy = base_y + offset
            draw.ellipse(
                (cx, cy, cx + r, cy + r),
                fill=theme.background,
                outline=theme.border,
            )

    # Text
    text_box = (padding + 12, padding + 12, width - padding - 24, height - padding - 56)
    wrapped = wrap_text(draw, cleaned, text_box[2] - text_box[0], font=font)
    draw.multiline_text(
        (text_box[0], text_box[1]),
        wrapped,
        fill=theme.text,
        font=font,
        spacing=4,
    )

    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "PNG")
    logger.info("Overlay saved to %s", out_path)
    return out_path


def render_empty_overlay(output_path: str | Path, size: Tuple[int, int] = DEFAULT_SIZE) -> Path:
    """
    Write a fully transparent image to clear the overlay.
    """
    width, height = size
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "PNG")
    logger.info("Overlay cleared at %s", out_path)
    return out_path


def wrap_text(draw: ImageDraw.ImageDraw, text: str, max_width: int, font) -> str:
    words = text.split()
    lines = []
    current = []
    for word in words:
        candidate = " ".join(current + [word])
        w, _ = _measure(draw, candidate, font)
        if w <= max_width:
            current.append(word)
        else:
            if current:
                lines.append(" ".join(current))
            current = [word]
    if current:
        lines.append(" ".join(current))
    return "\n".join(lines)


def _measure(draw: ImageDraw.ImageDraw, text: str, font) -> tuple[int, int]:
    """
    Measure text width/height with Pillow version compatibility.
    """
    if hasattr(draw, "textbbox"):
        bbox = draw.textbbox((0, 0), text, font=font)
        return bbox[2] - bbox[0], bbox[3] - bbox[1]
    # Fallback for older Pillow
    if hasattr(draw, "textsize"):
        return draw.textsize(text, font=font)
    # Last resort approximate length
    return (len(text) * 7, 12)


def _get_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    if size in DEFAULT_FONT_CACHE:
        return DEFAULT_FONT_CACHE[size]
    try:
        DEFAULT_FONT_CACHE[size] = ImageFont.truetype("DejaVuSans.ttf", size=size)
        return DEFAULT_FONT_CACHE[size]
    except Exception:
        DEFAULT_FONT_CACHE[size] = ImageFont.load_default()
        return DEFAULT_FONT_CACHE[size]


def _clean_text(text: str) -> str:
    cleaned = text.strip()
    # Remove enclosing quotes if present
    if cleaned.startswith('"') and cleaned.endswith('"'):
        cleaned = cleaned[1:-1].strip()
    if cleaned.startswith("'") and cleaned.endswith("'"):
        cleaned = cleaned[1:-1].strip()
    return cleaned
