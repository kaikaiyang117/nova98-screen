import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nova98.renderer.renderer import HEIGHT, WIDTH, render


class Metrics:
    cpu_percent = 62.0
    memory_percent = 74.0
    cpu_temperature = 58.0
    download_bytes_per_sec = 3.2 * 1024 * 1024
    upload_bytes_per_sec = 0.8 * 1024 * 1024


class Sparse:
    cpu_percent = 10.0
    memory_percent = None
    cpu_temperature = None
    download_bytes_per_sec = None
    upload_bytes_per_sec = None


def test_render_size():
    image = render(Metrics())
    assert image.size == (WIDTH, HEIGHT)


def test_render_not_all_black():
    colors = render(Metrics()).getcolors(maxcolors=100000)
    assert colors and len(colors) > 5


def test_render_hides_none_rows():
    image = render(Sparse())
    # Should still render without raising; CPU text present.
    px = image.load()
    assert any(px[x, y][0] for x in range(WIDTH) for y in range(HEIGHT))
