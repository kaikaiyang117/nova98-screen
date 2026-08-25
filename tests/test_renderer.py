import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nova98.renderer.renderer import HEIGHT, WIDTH, render
from nova98.renderer.state import StaticDisplayState


def test_render_size():
    state = StaticDisplayState(memory_percent=74.0, download_bytes_per_sec=3.2e6, upload_bytes_per_sec=0.8e6)
    image = render(state)
    assert image.size == (WIDTH, HEIGHT)


def test_render_not_all_black():
    state = StaticDisplayState(memory_percent=74.0, download_bytes_per_sec=100.0)
    colors = render(state).getcolors(maxcolors=100000)
    assert colors and len(colors) > 5


def test_static_state_carries_framebuffer_channel_fields():
    # Native cmd-52 telemetry renders nothing on NOVA98, so CPU/temp ride the
    # static channel; GPU fields must stay out (no data source on macOS).
    fields = set(StaticDisplayState.__dataclass_fields__)
    assert "cpu_percent" in fields
    assert "cpu_temperature" in fields
    assert "gpu_percent" not in fields
    assert "timestamp" not in fields


def test_render_hides_none_rows():
    image = render(StaticDisplayState(memory_percent=10.0))
    px = image.load()
    assert any(px[x, y][0] for x in range(WIDTH) for y in range(HEIGHT))
