"""Static framebuffer upload statistics.

Semantics:
- frames_prepared: refresh candidates that produced a PreparedFrame
- frames_succeeded: candidates whose upload eventually succeeded
- wire_attempts / wire_failures: real USB upload tries (including retries)
- chunks_sent / chunks_acked: 4096-byte pages written vs ACKed
- skipped_*: candidates rejected before any render/upload

Frame-level counts are logical; wire counts are physical activity.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class StaticUploadStats:
    frames_prepared: int = 0
    frames_succeeded: int = 0
    wire_attempts: int = 0
    wire_failures: int = 0
    chunks_sent: int = 0
    chunks_acked: int = 0
    skipped_interval: int = 0
    skipped_unchanged: int = 0
    skipped_hash: int = 0

    def summary(self) -> str:
        return (
            f"frames(prepared/succeeded)={self.frames_prepared}/{self.frames_succeeded} "
            f"wire(attempts/failures)={self.wire_attempts}/{self.wire_failures} "
            f"chunks(sent/acked)={self.chunks_sent}/{self.chunks_acked} "
            f"skipped(interval/unchanged/hash)="
            f"{self.skipped_interval}/{self.skipped_unchanged}/{self.skipped_hash}"
        )
