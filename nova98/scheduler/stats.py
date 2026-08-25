"""Static framebuffer upload statistics: makes flash-write frequency observable."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class StaticUploadStats:
    attempted: int = 0
    succeeded: int = 0
    failed: int = 0
    skipped_interval: int = 0
    skipped_unchanged: int = 0
    skipped_hash: int = 0

    def summary(self) -> str:
        return (
            f"uploads={self.succeeded} attempted={self.attempted} failed={self.failed} "
            f"skipped(interval/unchanged/hash)="
            f"{self.skipped_interval}/{self.skipped_unchanged}/{self.skipped_hash}"
        )
