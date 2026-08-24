"""Network rate calculation from cumulative counters."""

from __future__ import annotations

import time

import psutil


class NetworkRateCalculator:
    def __init__(self) -> None:
        counters = psutil.net_io_counters()
        self._last_time = time.monotonic()
        self._last_rx = counters.bytes_recv
        self._last_tx = counters.bytes_sent
        self.download_bytes_per_sec: float | None = None
        self.upload_bytes_per_sec: float | None = None

    def update(self) -> tuple[float | None, float | None]:
        now = time.monotonic()
        dt = now - self._last_time
        if dt <= 0:
            return self.download_bytes_per_sec, self.upload_bytes_per_sec

        counters = psutil.net_io_counters()
        rx, tx = counters.bytes_recv, counters.bytes_sent
        if rx < self._last_rx or tx < self._last_tx:
            # Counter reset (reboot / interface change).
            self._last_rx, self._last_tx = rx, tx
            self._last_time = now
            return self.download_bytes_per_sec, self.upload_bytes_per_sec

        self.download_bytes_per_sec = (rx - self._last_rx) / dt
        self.upload_bytes_per_sec = (tx - self._last_tx) / dt
        self._last_rx, self._last_tx = rx, tx
        self._last_time = now
        return self.download_bytes_per_sec, self.upload_bytes_per_sec
