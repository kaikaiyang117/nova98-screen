"""Frame buffer assembly for NOVA98 uploads (real protocol, from AULA HUB JS).

Stream layout: 256-byte header + RGB565 little-endian frames,
chunked into 4096-byte payloads inside 4104-byte HID output reports.
Final chunk is zero-padded (not 0xFF).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from PIL import Image

from nova98.display.rgb565 import encode_rgb565
from nova98.device.profiles import DeviceProfile

HEADER_SIZE = 256
CHUNK_PAYLOAD_SIZE = 4096


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
    def sha256(self) -> str:
        return hashlib.sha256(self.payload).hexdigest()

    @property
    def chunk_count(self) -> int:
        return (len(self.payload) + CHUNK_PAYLOAD_SIZE - 1) // CHUNK_PAYLOAD_SIZE


def build_frame_buffer(image: Image.Image, profile: DeviceProfile) -> FrameBuffer:
    if image.size != (profile.width, profile.height):
        raise FrameBufferError(
            f"image is {image.size}, expected ({profile.width}, {profile.height})"
        )

    pixels = encode_rgb565(image)
    expected_pixels = profile.width * profile.height * 2
    if len(pixels) != expected_pixels:
        raise FrameBufferError(f"pixel buffer is {len(pixels)} bytes, expected {expected_pixels}")

    # 256-byte header: [0]=frame count, [1..N]=delays*5 (last forced 0),
    # remainder 0xFF. Single static frame => count=1, header[1]=0.
    header = bytearray(b"\xFF" * HEADER_SIZE)
    header[0] = 1
    header[1] = 0

    return FrameBuffer(
        profile_name=profile.name,
        width=profile.width,
        height=profile.height,
        frame_count=1,
        payload=bytes(header) + pixels,
    )


def iter_chunks(payload: bytes) -> list[bytes]:
    """Split payload into 4096-byte chunks, zero-padding the last."""
    chunks = []
    for i in range(0, len(payload), CHUNK_PAYLOAD_SIZE):
        chunks.append(payload[i : i + CHUNK_PAYLOAD_SIZE].ljust(CHUNK_PAYLOAD_SIZE, b"\x00"))
    return chunks
