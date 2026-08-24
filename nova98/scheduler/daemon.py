"""Background refresh loop with reconnect/backoff state machine."""

from __future__ import annotations

import hashlib
import logging
import time

from PIL import Image

from nova98.config import Config
from nova98.device.hid_device import HidError, Nova98Hid
from nova98.device.profiles import NOVA98
from nova98.display.framebuffer import build_frame_buffer
from nova98.display.uploader import SafetyError, UploadError, upload_single_frame
from nova98.metrics.base import SystemMetrics
from nova98.renderer.renderer import render
from nova98.scheduler.change_detector import ChangeDetector, Thresholds
from nova98.scheduler.refresh import RefreshLimiter

RECONNECT_INTERVAL_S = 5.0
BACKOFF_S = 60.0
MAX_UPLOAD_RETRIES = 3

logger = logging.getLogger(__name__)


class ScreenDaemon:
    states = ("CONNECTED", "DISCONNECTED", "RECONNECTING", "BACKOFF")

    def __init__(self, config: Config):
        self.config = config
        self.limiter = RefreshLimiter(
            min_interval=config.refresh.min_interval,
            force_interval=config.refresh.force_interval,
        )
        self.detector = ChangeDetector(
            thresholds=Thresholds(
                cpu=config.thresholds.cpu,
                memory=config.thresholds.memory,
                temperature=config.thresholds.temperature,
            )
        )
        self._hid: Nova98Hid | None = None
        self._last_frame_hash: str | None = None
        self._state = "DISCONNECTED"
        self._backoff_until = 0.0

    @property
    def state(self) -> str:
        return self._state

    # -- device lifecycle --------------------------------------------------

    def _try_connect(self) -> bool:
        try:
            if self._hid is None:
                self._hid = Nova98Hid(NOVA98)
                self._hid.open()
                logger.info("Device connected")
            else:
                self._hid.close()
                self._hid.open()
                logger.info("Device reconnected")
            self._state = "CONNECTED"
            return True
        except (HidError, OSError) as exc:
            logger.debug("Connect failed: %s", exc)
            self._state = "RECONNECTING"
            return False

    def disconnect(self) -> None:
        if self._hid is not None:
            self._hid.close()
            self._hid = None
        self._state = "DISCONNECTED"
        logger.info("Device disconnected")

    # -- main loop -----------------------------------------------------------

    def tick(self, metrics: SystemMetrics) -> bool:
        """One decision cycle. Returns True if a frame was uploaded."""
        if self._state == "BACKOFF":
            if time.monotonic() < self._backoff_until:
                return False
            self._state = "DISCONNECTED"

        if self._state != "CONNECTED":
            if not self._try_connect():
                return False

        try:
            return self._update(metrics)
        except (UploadError, SafetyError, HidError, OSError) as exc:
            logger.warning("Update failed: %s", exc)
            self.disconnect()
            return False

    def _update(self, metrics: SystemMetrics) -> bool:
        assert self._hid is not None
        significant = self.detector.significant_change(metrics)

        if self.limiter.must_force():
            reason = "forced"
        elif not self.limiter.allow():
            logger.debug("Frame skipped: min interval not reached")
            return False
        elif significant:
            reason = "changed"
        else:
            logger.debug("Frame skipped: no significant change")
            return False

        image = render(metrics)
        frame = build_frame_buffer(image, NOVA98)
        digest = frame.sha256
        if digest == self._last_frame_hash:
            logger.info("Frame skipped: identical hash")
            self.limiter.mark_updated()
            return False

        for attempt in range(1, MAX_UPLOAD_RETRIES + 1):
            try:
                upload_single_frame(image, self._hid)
                self._last_frame_hash = digest
                self.limiter.mark_updated()
                logger.info("Screen updated (%s), attempt %d", reason, attempt)
                return True
            except (UploadError, HidError, OSError) as exc:
                logger.warning("Upload attempt %d failed: %s", attempt, exc)
                time.sleep(1.0)

        self._state = "BACKOFF"
        self._backoff_until = time.monotonic() + BACKOFF_S
        logger.error("Upload failed %d times, entering BACKOFF for %ds", MAX_UPLOAD_RETRIES, BACKOFF_S)
        return False

    # -- helpers ---------------------------------------------------------

    @staticmethod
    def preview(metrics: SystemMetrics) -> Image.Image:
        return render(metrics)


def frame_hash(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()
