"""Frame buffer assembly for single-frame uploads.

Layout follows the F108 Pro family format (see docs/protocol.md):
256-byte header + 240*135*2 pixel bytes, page-padded to a multiple of 4096.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from PIL import Image

from nova98.display.rgb565 import encode_rgb565
from nova98.device.profiles import DeviceProfile

HEADER_SIZE = 256
PAGE_SIZE = 4096
PAD_BYTE = 0xFF


class FrameBufferError(ValueError):
    pass


@dataclass(frozen=True)
class FrameBuffer:
    profile_name: str
    width: int
    height: int
    frame_count: int
    payload: bytes

    @property
    def size(self) -> int:
        return len(self.payload)

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.payload).hexdigest()


def build_frame_buffer(image: Image.Image, profile: DeviceProfile) -> FrameBuffer:
    if image.size != (profile.width, profile.height):
        raise FrameBufferError(
            f"image is {image.size}, expected ({profile.width}, {profile.height})"
        )

    pixels = encode_rgb565(image)
    expected_pixels = profile.width * profile.height * 2
    if len(pixels) != expected_pixels:
        raise FrameBufferError(f"pixel buffer is {len(pixels)} bytes, expected {expected_pixels}")

    body = bytearray()
    body += HEADER_SIZE.to_bytes(2, "little")          # gif_headlength = 256
    body += (1).to_bytes(2, "little")                  # frame count = 1
    body += b"\x00" * (HEADER_SIZE - len(body))        # rest of header unused

    body += pixels

    remainder = len(body) % PAGE_SIZE
    if remainder:
        body += b"\xFF" * (PAGE_SIZE - remainder)

    return FrameBuffer(
        profile_name=profile.name,
        width=profile.width,
        height=profile.height,
        frame_count=1,
        payload=bytes(body),
    )
