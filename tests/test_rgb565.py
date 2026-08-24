import pytest
from PIL import Image

from nova98.display.rgb565 import encode_rgb565, rgb888_to_rgb565


def test_single_pixel_conversions():
    assert rgb888_to_rgb565(0x00, 0x00, 0x00) == 0x0000
    assert rgb888_to_rgb565(0xFF, 0xFF, 0xFF) == 0xFFFF
    assert rgb888_to_rgb565(0xFF, 0x00, 0x00) == 0xF800
    assert rgb888_to_rgb565(0x00, 0xFF, 0x00) == 0x07E0
    assert rgb888_to_rgb565(0x00, 0x00, 0xFF) == 0x001F


@pytest.mark.parametrize(
    "color, expected",
    [
        ((0, 0, 0), 0x0000),
        ((255, 255, 255), 0xFFFF),
        ((255, 0, 0), 0xF800),
        ((0, 255, 0), 0x07E0),
        ((0, 0, 255), 0x001F),
    ],
)
def test_encode_flat_images(color, expected):
    image = Image.new("RGB", (240, 135), color)
    buf = encode_rgb565(image)
    assert len(buf) == 240 * 135 * 2 == 64800
    # Little-endian byte order.
    word = buf[0] | (buf[1] << 8)
    assert word == expected


def test_encode_gradient_size_and_order():
    image = Image.new("RGB", (4, 1))
    image.putpixel((0, 0), (255, 255, 255))
    image.putpixel((1, 0), (0, 0, 0))
    image.putpixel((2, 0), (248, 252, 248))  # exact max-ish values
    image.putpixel((3, 0), (7, 3, 7))
    buf = encode_rgb565(image)
    assert len(buf) == 8
    words = [buf[i] | (buf[i + 1] << 8) for i in range(0, 8, 2)]
    assert words == [0xFFFF, 0x0000, 0xFFFF, 0x0000]
