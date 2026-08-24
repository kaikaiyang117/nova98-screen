"""Change detection: only refresh when values moved beyond thresholds."""

from __future__ import annotations

from dataclasses import dataclass, field

from nova98.metrics.base import SystemMetrics


@dataclass
class Thresholds:
    cpu: float = 10.0
    memory: float = 5.0
    temperature: float = 3.0
    network_tier_bytes: float = 512 * 1024  # rate changes across tier boundaries


@dataclass
class ChangeDetector:
    thresholds: Thresholds = field(default_factory=Thresholds)
    _last: SystemMetrics | None = None
    _last_minute: str | None = None

    def significant_change(self, metrics: SystemMetrics) -> bool:
        changed = self._compare(metrics) or (metrics.minute_key() != self._last_minute)
        self._last = metrics
        self._last_minute = metrics.minute_key()
        return changed

    def _moved(self, old: float | None, new: float | None, threshold: float) -> bool:
        if old is None and new is None:
            return False
        if old is None or new is None:
            return True
        return abs(new - old) >= threshold

    def _tier(self, value: float | None) -> int:
        if value is None:
            return -1
        return int(value // self.thresholds.network_tier_bytes)

    def _compare(self, metrics: SystemMetrics) -> bool:
        last = self._last
        if last is None:
            return True
        t = self.thresholds
        return (
            self._moved(last.cpu_percent, metrics.cpu_percent, t.cpu)
            or self._moved(last.memory_percent, metrics.memory_percent, t.memory)
            or self._moved(last.cpu_temperature, metrics.cpu_temperature, t.temperature)
            or self._tier(last.download_bytes_per_sec) != self._tier(metrics.download_bytes_per_sec)
            or self._tier(last.upload_bytes_per_sec) != self._tier(metrics.upload_bytes_per_sec)
        )
