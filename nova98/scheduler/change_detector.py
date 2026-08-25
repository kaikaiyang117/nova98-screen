"""Static change detection: compares against the LAST COMMITTED (displayed)
state, not the previous sample, so slow drift still triggers an update.

Detects every field rendered by the static framebuffer channel:
CPU usage, CPU temperature, RAM and network rate tiers.
(GPU fields have no data source enabled by default.)
"""

from __future__ import annotations

from dataclasses import dataclass

from nova98.renderer.state import StaticDisplayState


@dataclass(frozen=True)
class StaticThresholds:
    memory: float = 5.0
    cpu: float = 10.0
    temperature: float = 3.0
    network_tier_bytes: float = 512 * 1024  # rate changes across tier boundaries


class StaticChangeDetector:
    """Pure comparison: changed(last_committed, current) -> bool.

    The caller owns `_last_committed_state` and must only advance it after a
    successful frame upload.
    """

    def __init__(self, thresholds: StaticThresholds | None = None):
        self.thresholds = thresholds or StaticThresholds()

    def changed(
        self,
        last_committed: StaticDisplayState | None,
        current: StaticDisplayState,
    ) -> bool:
        if last_committed is None:
            return True
        t = self.thresholds
        return (
            self._moved(last_committed.memory_percent, current.memory_percent, t.memory)
            or self._moved(last_committed.cpu_percent, current.cpu_percent, t.cpu)
            or self._moved(
                last_committed.cpu_temperature, current.cpu_temperature, t.temperature
            )
            or self._tier(last_committed.download_bytes_per_sec)
            != self._tier(current.download_bytes_per_sec)
            or self._tier(last_committed.upload_bytes_per_sec)
            != self._tier(current.upload_bytes_per_sec)
        )

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


# Backwards-compatible alias for existing imports.
Thresholds = StaticThresholds
