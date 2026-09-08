"""Key image rendering.

The Mini protocol writes a raster image per key. We bake color + identity +
label into a single image so a stale title can never survive an otherwise-black
key (research section 9). The exact on-device pixel format (size, channel
layout, packet framing) is Mini-specific and is validated by tools/probe_device.py;
this module produces clean RGB pixels that the HID layer frames.
"""

from __future__ import annotations

from typing import Optional

from .model import APPEARANCE_COLOR, APPEARANCE_LABEL, DisplayAppearance

# Mini key resolution. The Mini differs from the larger models, so this is a
# configurable default that probe_device.py confirms against the real device.
DEFAULT_KEY_SIZE = 144


def _hex_to_rgb(hexc: str) -> tuple[int, int, int]:
    h = hexc.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def _font(size: int):
    from PIL import ImageFont

    for path in (
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/consola.ttf",
    ):
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _draw_centered(draw, text: str, size: int, y_center: int, font) -> None:
    try:
        l, t, r, b = draw.textbbox((0, 0), text, font=font)
        tw, th = r - l, b - t
    except Exception:
        tw, th = len(text) * 8, 12
    x = (size - tw) // 2 - l
    y = y_center - th // 2 - t
    draw.text((x, y), text, fill=(10, 10, 10), font=font)


def render_key(
    appearance: DisplayAppearance,
    identity: str = "",
    label: Optional[str] = None,
    size: int = DEFAULT_KEY_SIZE,
) -> bytes:
    """Render one key as raw RGB bytes (size x size x 3, top-down rows).

    The appearance color is always authoritative; label defaults to the state
    word (RUN/IDLE/INPUT/?) and identity is a short second line.
    """
    from PIL import Image, ImageDraw

    if label is None:
        label = APPEARANCE_LABEL[appearance]

    bg = _hex_to_rgb(APPEARANCE_COLOR[appearance])
    img = Image.new("RGB", (size, size), bg)
    draw = ImageDraw.Draw(img)

    if appearance is not DisplayAppearance.BLACK and (label or identity):
        big = _font(size // 5)
        small = _font(size // 8)
        if label:
            _draw_centered(draw, label, size, size // 3, big)
        if identity:
            _draw_centered(draw, _short(identity), size, (size * 2) // 3, small)

    return img.tobytes()


def _short(text: str, n: int = 12) -> str:
    text = text.strip()
    return text if len(text) <= n else text[: n - 1] + "."


def black_frame(size: int = DEFAULT_KEY_SIZE) -> bytes:
    """Solid black key (no live instance)."""
    from PIL import Image

    img = Image.new("RGB", (size, size), (0, 0, 0))
    return img.tobytes()
