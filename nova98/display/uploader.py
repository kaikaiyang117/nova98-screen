"""Safe single-frame uploader for NOVA98.

Real protocol (reverse-engineered from AULA HUB WebHID JS, docs/protocol.md):
- image stream goes out on the 0xFF67 interface (interface 3) as 4104-byte
  output reports: AA 50 <idx LE16> <total LE16> 50 06 + 4096 payload bytes
- each chunk must be ACKed by an input report 55 41 ...
- there is NO begin/apply handshake

Hard limits: exactly 1 frame, exact panel size, no raw flash addressing.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from PIL import Image

from nova98.device.hid_device import Nova98Hid
from nova98.device.profiles import DeviceProfile
from nova98.display.framebuffer import build_frame_buffer, iter_chunks

MAX_TEST_FRAMES = 1

CMD_SET_TFT_USER_ANIMATION = 0x50
ACK_CMD_SET_LED_USER_ANIMATION = 0x41
ACK_MAGIC = 0x55
HEADER_CONSTANT = b"\x50\x06"  # literal 6619136/4096 = 0x0650, verbatim from HUB

logger = logging.getLogger(__name__)


class SafetyError(RuntimeError):
    pass


class UploadError(IOError):
    pass


@dataclass(frozen=True)
class UploadResult:
    pages: int
    acks: int
    duration_s: float


def _validate(frame, profile: DeviceProfile) -> None:
    if frame.frame_count != MAX_TEST_FRAMES:
        raise SafetyError(f"frame_count={frame.frame_count}, test uploads allow only {MAX_TEST_FRAMES}")
    if frame.width != profile.width or frame.height != profile.height:
        raise SafetyError(
            f"frame is {frame.width}x{frame.height}, expected {profile.width}x{profile.height}"
        )
    if frame.chunk_count > 64:
        raise SafetyError(f"chunk count {frame.chunk_count} exceeds sanity limit")


def _chunk_header(index: int, total: int) -> bytes:
    return bytes(
        (
            0xAA,
            CMD_SET_TFT_USER_ANIMATION,
            index & 0xFF,
            (index >> 8) & 0xFF,
            total & 0xFF,
            (total >> 8) & 0xFF,
            HEADER_CONSTANT[0],
            HEADER_CONSTANT[1],
        )
    )


def upload_single_frame(image: Image.Image, hid_dev: Nova98Hid) -> UploadResult:
    profile = hid_dev.profile
    frame = build_frame_buffer(image, profile)
    _validate(frame, profile)

    chunks = iter_chunks(frame.payload)
    total = len(chunks)
    logger.info("Frame upload started: %d chunks, sha256=%s", total, frame.sha256[:16])
    start = time.monotonic()

    acks = 0
    for i, body in enumerate(chunks):
        try:
            ack = hid_dev.write_tft_chunk(_chunk_header(i, total) + body)
        except (IOError, OSError) as exc:
            raise UploadError(f"chunk {i}: {exc}") from exc
        if ack is None or len(ack) < 2 or ack[0] != ACK_MAGIC or ack[1] != ACK_CMD_SET_LED_USER_ANIMATION:
            raise UploadError(
                f"chunk {i}: bad/no ACK ({ack.hex(' ') if ack else 'timeout'})"
            )
        acks += 1

    duration = time.monotonic() - start
    logger.info("Frame upload finished in %.1fs (%d/%d ACKs)", duration, acks, total)
    return UploadResult(pages=total, acks=acks, duration_s=duration)
