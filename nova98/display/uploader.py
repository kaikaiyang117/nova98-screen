"""Safe single-frame uploader for NOVA98.

Hard limits (see docs/protocol.md and the execution plan):
- exactly 1 frame per upload
- exact panel dimensions
- payload padded to a whole number of pages
- no raw flash addressing exposed
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from PIL import Image

from nova98.device.hid_device import Nova98Hid
from nova98.device.profiles import DeviceProfile
from nova98.display.framebuffer import PAGE_SIZE, FrameBuffer, build_frame_buffer

MAX_TEST_FRAMES = 1
CMD_DELAY_S = 0.035

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


def _validate(frame: FrameBuffer, profile: DeviceProfile) -> None:
    if frame.frame_count != MAX_TEST_FRAMES:
        raise SafetyError(f"frame_count={frame.frame_count}, test uploads allow only {MAX_TEST_FRAMES}")
    if frame.width != profile.width or frame.height != profile.height:
        raise SafetyError(
            f"frame is {frame.width}x{frame.height}, expected {profile.width}x{profile.height}"
        )
    if frame.size % PAGE_SIZE != 0 or frame.size > PAGE_SIZE * 64:
        raise SafetyError(f"payload size {frame.size} is not a sane page multiple")


def _image_header_command(slot: int, page_count: int) -> bytes:
    # F108 Pro layout: 04 72 <slot> ... <page_count LE16 @ offset 8..9>
    cmd = bytearray(64)
    cmd[0] = 0x04
    cmd[1] = 0x72
    cmd[2] = slot & 0xFF
    cmd[8] = page_count & 0xFF
    cmd[9] = (page_count >> 8) & 0xFF
    return bytes(cmd)


def upload_single_frame(image: Image.Image, hid_dev: Nova98Hid, slot: int = 0) -> UploadResult:
    """Upload one frame. Raises SafetyError on any limit violation."""
    profile = hid_dev.profile
    frame = build_frame_buffer(image, profile)
    _validate(frame, profile)

    page_count = frame.size // PAGE_SIZE
    logger.info("Frame upload started: %d pages, sha256=%s", page_count, frame.sha256[:16])
    start = time.monotonic()

    begin_ack = hid_dev.send_command(bytes.fromhex("0418"))
    logger.debug("BEGIN ack: %s", begin_ack.hex(" ") if begin_ack else "<none>")
    if begin_ack is not None and begin_ack[1:3] != b"\x04\x18":
        raise UploadError(f"BEGIN rejected: {begin_ack.hex(' ')}")

    header_ack = hid_dev.send_command(_image_header_command(slot, page_count))
    logger.debug("HEADER ack: %s", header_ack.hex(" ") if header_ack else "<none>")
    if header_ack is None or header_ack[1:2] != b"\x04":
        raise UploadError(f"image header rejected: {header_ack.hex(' ') if header_ack else '<none>'}")

    payload = frame.payload
    acks = 0
    for i in range(page_count):
        page = payload[i * PAGE_SIZE : (i + 1) * PAGE_SIZE]
        try:
            ack = hid_dev.write_page(page)
        except (IOError, OSError) as exc:
            raise UploadError(f"page {i}: {exc}") from exc
        if ack:
            acks += 1
        time.sleep(CMD_DELAY_S)

    apply_ack = hid_dev.send_command(bytes.fromhex("0402"))
    logger.debug("APPLY ack: %s", apply_ack.hex(" ") if apply_ack else "<none>")
    if apply_ack is None or apply_ack[1:2] != b"\x04":
        raise UploadError(f"APPLY rejected: {apply_ack.hex(' ') if apply_ack else '<none>'}")

    duration = time.monotonic() - start
    logger.info("Frame upload finished in %.1fs (%d/%d page ACKs)", duration, acks, page_count)
    return UploadResult(pages=page_count, acks=acks, duration_s=duration)
