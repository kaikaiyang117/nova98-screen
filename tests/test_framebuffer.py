import pytest
from PIL import Image

from nova98.device.profiles import NOVA98
from nova98.display.framebuffer import (
    CHUNK_PAYLOAD_SIZE,
    FrameBufferError,
    build_frame_buffer,
    iter_chunks,
)


def test_single_frame_payload_layout():
    image = Image.new("RGB", (NOVA98.width, NOVA98.height), (0, 0, 0))
    fb = build_frame_buffer(image, NOVA98)

    assert fb.frame_count == 1
    # 256-byte header + 64800 pixel bytes.
    assert len(fb.payload) == 256 + NOVA98.width * NOVA98.height * 2
    assert fb.chunk_count == 16
    chunks = iter_chunks(fb.payload)
    assert len(chunks) == 16
    assert all(len(c) == CHUNK_PAYLOAD_SIZE for c in chunks)
    # Last chunk is zero-padded.
    assert chunks[15][:3616] == fb.payload[15 * CHUNK_PAYLOAD_SIZE :]
    assert all(b == 0 for b in chunks[15][3616:])


def test_header_layout():
    image = Image.new("RGB", (NOVA98.width, NOVA98.height), (0, 0, 0))
    fb = build_frame_buffer(image, NOVA98)
    assert fb.payload[0] == 1      # frame count
    assert fb.payload[1] == 0      # single-frame delay slot forced 0


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
