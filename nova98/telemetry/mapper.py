"""SystemMetrics -> TelemetryStatus mapping. No psutil below this line."""

from __future__ import annotations

from nova98.metrics.base import SystemMetrics
from nova98.telemetry.model import TelemetryStatus


def _usage(value: float | None) -> int | None:
    if value is None:
        return None
    return max(0, min(100, round(value)))


def _temperature(value: float | None) -> int | None:
    if value is None:
        return None
    return max(-127, min(127, round(value)))


def metrics_to_telemetry(metrics: SystemMetrics) -> TelemetryStatus:
    return TelemetryStatus(
        cpu_usage=_usage(metrics.cpu_percent),
        cpu_temperature=_temperature(metrics.cpu_temperature),
        gpu_usage=_usage(metrics.gpu_percent),
        gpu_temperature=_temperature(metrics.gpu_temperature),
    )
