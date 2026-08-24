from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class SystemMetrics:
    cpu_percent: float | None = None
    memory_percent: float | None = None
    cpu_temperature: float | None = None
    gpu_percent: float | None = None
    gpu_temperature: float | None = None
    download_bytes_per_sec: float | None = None
    upload_bytes_per_sec: float | None = None
    timestamp: datetime | None = None

    def minute_key(self) -> str:
        ts = self.timestamp or datetime.now()
        return ts.strftime("%Y%m%d%H%M")
