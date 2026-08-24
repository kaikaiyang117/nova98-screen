"""Dashboard renderer. Receives a SystemMetrics-like object; never touches psutil or USB."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Protocol

from PIL import Image, ImageDraw

WIDTH = 240
HEIGHT = 135


class RenderMetrics(Protocol):
    cpu_percent: float | None
    memory_percent: float | None
    cpu_temperature: float | None
    download_bytes_per_sec: float | None
    upload_bytes_per_sec: float | None


@dataclass(frozen=True)
class Theme:
    background: tuple[int, int, int] = (0, 0, 0)
    text: tuple[int, int, int] = (255, 255, 255)
    dim_text: tuple[int, int, int] = (140, 140, 140)
    accent: tuple[int, int, int] = (0, 200, 120)
    warn: tuple[int, int, int] = (255, 170, 0)
    hot: tuple[int, int, int] = (255, 60, 60)
    bar_track: tuple[int, int, int] = (50, 50, 50)


def _font(size: int):
    from PIL import ImageFont

    for name in ("DejaVuSansMono-Bold.ttf", "Menlo.ttc", "Monaco.dfont"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _level_color(value: float, theme: Theme) -> tuple[int, int, int]:
    if value >= 85:
        return theme.hot
    if value >= 60:
        return theme.warn
    return theme.accent


def _format_rate(value: float | None) -> str:
    if value is None:
        return "--"
    for unit in ("B/s", "KB/s", "MB/s", "GB/s"):
        if value < 1024:
            return f"{value:.1f}{unit}" if unit != "B/s" else f"{value:.0f}B/s"
        value /= 1024
    return f"{value:.1f}TB/s"


def render(metrics: RenderMetrics, theme: Theme | None = None) -> Image.Image:
    """Render the 240x135 dashboard. None values hide their row."""
    theme = theme or Theme()
    image = Image.new("RGB", (WIDTH, HEIGHT), theme.background)
    draw = ImageDraw.Draw(image)

    font_label = _font(13)
    font_value = _font(13)
    font_header = _font(17)
    font_footer = _font(12)

    # Header: clock left, title right.
    now = time.strftime("%H:%M")
    draw.text((10, 6), now, font=font_header, fill=theme.text)
    title = "SYSTEM"
    tw = draw.textlength(title, font=font_label)
    draw.text((WIDTH - tw - 10, 9), title, font=font_label, fill=theme.dim_text)
    draw.line([(8, 28), (WIDTH - 8, 28)], fill=theme.bar_track, width=1)

    rows = [
        ("CPU", metrics.cpu_percent, "%"),
        ("TEMP", metrics.cpu_temperature, "\u00b0C"),
        ("RAM", metrics.memory_percent, "%"),
    ]
    y = 36
    row_h = 27
    bar_x, bar_w = 62, 110
    for label, value, suffix in rows:
        if value is None:
            continue
        pct = max(0.0, min(100.0, float(value)))
        color = _level_color(pct, theme)
        draw.text((10, y + 3), label, font=font_label, fill=theme.dim_text)
        # Track then filled portion; 6px tall to avoid hairlines.
        draw.rectangle([bar_x, y + 5, bar_x + bar_w, y + 11], fill=theme.bar_track)
        filled = round(bar_w * pct / 100)
        if filled > 0:
            draw.rectangle([bar_x, y + 5, bar_x + filled, y + 11], fill=color)
        text = f"{value:.0f}{suffix}" if suffix == "%" else f"{value:.0f}{suffix}"
        vw = draw.textlength(text, font=font_value)
        draw.text((WIDTH - 10 - vw, y + 2), text, font=font_value, fill=color)
        y += row_h

    # Footer: network rates.
    fy = HEIGHT - 20
    down = _format_rate(metrics.download_bytes_per_sec)
    up = _format_rate(metrics.upload_bytes_per_sec)
    draw.line([(8, fy - 6), (WIDTH - 8, fy - 6)], fill=theme.bar_track, width=1)
    draw.text((10, fy), f"\u2193 {down}", font=font_footer, fill=theme.dim_text)
    uw = draw.textlength(f"\u2191 {up}", font=font_footer)
    draw.text((WIDTH - 10 - uw, fy), f"\u2191 {up}", font=font_footer, fill=theme.dim_text)

    return image
