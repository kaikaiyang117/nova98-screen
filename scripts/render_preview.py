"""Render a static dashboard preview with fake data (no psutil, no USB)."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nova98.renderer.renderer import render


@dataclass
class FakeMetrics:
    cpu_percent: float | None = 62.0
    memory_percent: float | None = 74.0
    cpu_temperature: float | None = 58.0
    download_bytes_per_sec: float | None = 3.2 * 1024 * 1024
    upload_bytes_per_sec: float | None = 0.8 * 1024 * 1024


def main() -> int:
    out = Path("dashboard-preview.png")
    image = render(FakeMetrics())
    image.save(out)
    print(f"Saved {out} ({image.size[0]}x{image.size[1]})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
