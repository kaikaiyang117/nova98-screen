import pytest
from PIL import Image

from nova98.device.profiles import NOVA98
from nova98.display.framebuffer import (
    HEADER_SIZE,
    PAGE_SIZE,
    FrameBufferError,
    build_frame_buffer,
)


def test_single_frame_payload_layout():
    image = Image.new("RGB", (NOVA98.width, NOVA98.height), (0, 0, 0))
    fb = build_frame_buffer(image, NOVA98)

    assert fb.frame_count == 1
    # 256-byte header + 64800 pixels = 65056, page-padded to 16 * 4096.
    assert HEADER_SIZE + NOVA98.width * NOVA98.height * 2 == 65056
    assert fb.size == 16 * PAGE_SIZE == 65536


def test_rejects_wrong_dimensions():
    image = Image.new("RGB", (128, 64), (0, 0, 0))
    with pytest.raises(FrameBufferError):
        build_frame_buffer(image, NOVA98)


def test_deterministic_hash():
    image = Image.new("RGB", (NOVA98.width, NOVA98.height), (10, 20, 30))
    a = build_frame_buffer(image, NOVA98)
    b = build_frame_buffer(image.copy(), NOVA98)
    assert a.sha256 == b.sha256
    c = build_frame_buffer(Image.new("RGB", image.size, (220, 180, 90)), NOVA98)
    assert a.sha256 != c.sha256
