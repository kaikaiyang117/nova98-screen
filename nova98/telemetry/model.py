"""Native telemetry data model (cmd 52 system status overlay)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TelemetryStatus:
    cpu_usage: int | None = None
    cpu_temperature: int | None = None

    gpu_usage: int | None = None
    gpu_temperature: int | None = None

    temperature_current: int | None = None
    temperature_high: int | None = None
    temperature_low: int | None = None

    weather_code: int | None = None
    humidity: int | None = None
