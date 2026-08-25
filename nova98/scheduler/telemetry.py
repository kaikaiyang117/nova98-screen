"""Telemetry scheduler: fast-path decision for cmd 52 updates.

Semantics:
- should_send() is a PURE decision; it never mutates state.
- mark_sent(status) commits state ONLY after a successful HID send.
- interval_s is a hard min-interval; force_interval_s forces periodic sync.
"""

from __future__ import annotations

import time

from nova98.telemetry.model import TelemetryStatus


class TelemetryScheduler:
    def __init__(
        self,
        interval_s: float = 1.0,
        force_interval_s: float = 5.0,
        cpu_delta: int = 1,
        gpu_delta: int = 1,
        temperature_delta: int = 1,
    ):
        if interval_s <= 0:
            raise ValueError("interval_s must be positive")
        if force_interval_s < interval_s:
            raise ValueError("force_interval_s must be >= interval_s")
        self.interval_s = interval_s
        self.force_interval_s = force_interval_s
        self.cpu_delta = cpu_delta
        self.gpu_delta = gpu_delta
        self.temperature_delta = temperature_delta
        self._last: TelemetryStatus | None = None
        self._last_sent: float | None = None

    def reset(self) -> None:
        self._last = None
        self._last_sent = None

    def should_send(self, status: TelemetryStatus) -> bool:
        """Pure check against the last COMMITTED (successfully sent) status."""
        now = time.monotonic()
        if self._last_sent is not None:
            elapsed = now - self._last_sent
            if elapsed < self.interval_s:
                return False
            if elapsed >= self.force_interval_s:
                return True
        # First send ever, or meaningful change vs committed baseline.
        return self._last is None or self._moved_beyond_threshold(self._last, status)

    def mark_sent(self, status: TelemetryStatus) -> None:
        """Commit AFTER the HID send succeeded."""
        self._last = status
        self._last_sent = time.monotonic()

    def _moved_beyond_threshold(self, old: TelemetryStatus, new: TelemetryStatus) -> bool:
        return (
            self._field_moved(old.cpu_usage, new.cpu_usage, self.cpu_delta)
            or self._field_moved(old.gpu_usage, new.gpu_usage, self.gpu_delta)
            or self._field_moved(
                old.cpu_temperature, new.cpu_temperature, self.temperature_delta
            )
            or self._field_moved(
                old.gpu_temperature, new.gpu_temperature, self.temperature_delta
            )
        )

    @staticmethod
    def _field_moved(old: int | None, new: int | None, delta: int) -> bool:
        if old == new:
            return False
        if old is None or new is None:
            return True
        return abs(new - old) >= delta
