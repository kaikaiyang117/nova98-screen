"""CachedMetricProvider: throttles expensive hardware sampling (temp/GPU).

Wraps any zero-argument read callable; returns the cached value between
samples so a 1Hz metrics loop does not spawn powermetrics every second.
"""

from __future__ import annotations

import logging
import time
from typing import Callable

logger = logging.getLogger(__name__)


class CachedMetric:
    """Caches a callable's result for `interval_s` seconds.

    On failure the last good value is kept until it expires.
    """

    def __init__(self, reader: Callable[[], object], interval_s: float):
        if interval_s <= 0:
            raise ValueError("interval_s must be positive")
        self._reader = reader
        self._interval_s = interval_s
        self._value: object | None = None
        self._sampled_at: float | None = None

    def get(self):
        now = time.monotonic()
        if self._sampled_at is not None and (now - self._sampled_at) < self._interval_s:
            return self._value
        try:
            self._value = self._reader()
        except Exception as exc:  # noqa: BLE001 - sampling must never crash the loop
            logger.debug("cached metric sample failed: %s", exc)
            # keep previous value
        self._sampled_at = now
        return self._value
