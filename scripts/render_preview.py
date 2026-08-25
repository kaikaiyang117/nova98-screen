"""Render a static dashboard preview with fake data (no psutil, no USB)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nova98.renderer.renderer import render
from nova98.renderer.state import StaticDisplayState


def main() -> int:
    out = Path("dashboard-preview.png")
    image = render(
        StaticDisplayState(
            memory_percent=74.0,
            download_bytes_per_sec=3.2 * 1024 * 1024,
            upload_bytes_per_sec=0.8 * 1024 * 1024,
        )
    )
    image.save(out)
    print(f"Saved {out} ({image.size[0]}x{image.size[1]})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
