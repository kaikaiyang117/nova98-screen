"""Refresh limiter: screen updates are expensive flash writes; throttle them."""

from __future__ import annotations

import time


class RefreshLimiter:
    def __init__(self, min_interval: float = 30.0, force_interval: float = 300.0):
        if min_interval <= 0 or force_interval < min_interval:
            raise ValueError("require 0 < min_interval <= force_interval")
        self.min_interval = min_interval
        self.force_interval = force_interval
        self._last_update: float | None = None

    def reset(self) -> None:
        self._last_update = time.monotonic()

    def allow(self) -> bool:
        """True if an update is permitted right now (min interval passed)."""
        if self._last_update is None:
            return True
        return (time.monotonic() - self._last_update) >= self.min_interval

    def must_force(self) -> bool:
        """True if the force interval has elapsed regardless of change."""
        if self._last_update is None:
            return True
        return (time.monotonic() - self._last_update) >= self.force_interval

    def mark_updated(self) -> None:
        self._last_update = time.monotonic()
