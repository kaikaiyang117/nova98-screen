"""RGB565 encoding: PIL RGB888 image -> little-endian RGB565 byte buffer."""

from __future__ import annotations

import numpy as np
from PIL import Image


def rgb888_to_rgb565(r: int, g: int, b: int) -> int:
    """Convert one RGB888 pixel to an RGB565 value (RRRRRGGG GGGBBBBB)."""
    return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)


def encode_rgb565(image: Image.Image) -> bytes:
    """Encode a PIL image as little-endian RGB565 bytes.

    The image is converted to RGB and must match the expected size.
    """
    rgb = image.convert("RGB")
    arr = np.asarray(rgb, dtype=np.uint16)
    r = (arr[:, :, 0] & 0xF8) << 8
    g = (arr[:, :, 1] & 0xFC) << 3
    b = arr[:, :, 2] >> 3
    pixels = r | g | b
    return pixels.astype("<u2").tobytes()
