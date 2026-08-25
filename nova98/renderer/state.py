"""Static display data model: the ONLY input the static renderer accepts.

Dynamic metrics (CPU / GPU / temperatures) belong exclusively to the native
telemetry channel (cmd 52). Keeping them out of this type makes it a type
error to draw them back into the framebuffer.
"""

from __future__ import annotations

from dataclasses import dataclass

from nova98.metrics.base import SystemMetrics


@dataclass(frozen=True)
class StaticDisplayState:
    memory_percent: float | None = None
    download_bytes_per_sec: float | None = None
    upload_bytes_per_sec: float | None = None


def static_display_state(metrics: SystemMetrics) -> StaticDisplayState:
    """StaticMapper: SystemMetrics -> StaticDisplayState."""
    return StaticDisplayState(
        memory_percent=metrics.memory_percent,
        download_bytes_per_sec=metrics.download_bytes_per_sec,
        upload_bytes_per_sec=metrics.upload_bytes_per_sec,
    )
