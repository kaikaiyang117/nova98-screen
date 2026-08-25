"""Static display data model: the ONLY input the static renderer accepts.

NOTE (2026-08-25): the NOVA98 firmware ACKs cmd 52 system-status telemetry
but renders nothing, and official AULA HUB never calls it for this model
(verified against every frontend chunk). Until a working native channel
exists, CPU / CPU temperature are carried by the static frame like RAM.
"""

from __future__ import annotations

from dataclasses import dataclass

from nova98.metrics.base import SystemMetrics


@dataclass(frozen=True)
class StaticDisplayState:
    memory_percent: float | None = None
    cpu_percent: float | None = None
    cpu_temperature: float | None = None
    download_bytes_per_sec: float | None = None
    upload_bytes_per_sec: float | None = None


def static_display_state(metrics: SystemMetrics) -> StaticDisplayState:
    """StaticMapper: SystemMetrics -> StaticDisplayState."""
    return StaticDisplayState(
        memory_percent=metrics.memory_percent,
        cpu_percent=metrics.cpu_percent,
        cpu_temperature=metrics.cpu_temperature,
        download_bytes_per_sec=metrics.download_bytes_per_sec,
        upload_bytes_per_sec=metrics.upload_bytes_per_sec,
    )
