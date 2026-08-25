"""Dual-channel screen runtime: fast telemetry path + slow static frame path."""

from __future__ import annotations

import logging
import time

from PIL import Image

from nova98.config import Config
from nova98.device.hid_device import HidError, Nova98Hid
from nova98.device.profiles import NOVA98
from nova98.display.framebuffer import build_frame_buffer
from nova98.metrics.base import SystemMetrics
from nova98.renderer.renderer import render
from nova98.renderer.state import StaticDisplayState, static_display_state
from nova98.scheduler.change_detector import StaticChangeDetector, StaticThresholds
from nova98.scheduler.refresh import RefreshLimiter
from nova98.scheduler.telemetry import TelemetryScheduler
from nova98.telemetry.mapper import metrics_to_telemetry
from nova98.telemetry.model import TelemetryStatus
from nova98.telemetry.sender import TelemetrySender, TelemetryTransportError

RECONNECT_INTERVAL_S = 5.0
BACKOFF_S = 60.0
MAX_UPLOAD_RETRIES = 3

logger = logging.getLogger(__name__)


class DeviceSession:
    """Owns the single Nova98Hid connection (connect/reconnect/backoff)."""

    def __init__(self):
        self._hid: Nova98Hid | None = None

    @property
    def device(self) -> Nova98Hid:
        if self._hid is None:
            raise HidError("device not connected")
        return self._hid

    @property
    def connected(self) -> bool:
        return self._hid is not None

    def ensure_connected(self) -> bool:
        if self.connected:
            return True
        try:
            hid_dev = Nova98Hid(NOVA98)
            hid_dev.open()
            self._hid = hid_dev
            logger.info("Device connected")
            return True
        except (HidError, OSError) as exc:
            logger.debug("Connect failed: %s", exc)
            return False

    def disconnect(self) -> None:
        if self._hid is not None:
            try:
                self._hid.close()
            except OSError:
                pass
            self._hid = None
            logger.info("Device disconnected")


class TelemetryController:
    """FAST PATH: CPU/GPU/temp via cmd 52, ~1Hz, no framebuffer writes."""

    def __init__(self, scheduler):
        self.scheduler = scheduler
        self._sender: TelemetrySender | None = None
        self.enabled = True

    def bind(self, hid_dev: Nova98Hid) -> None:
        if self._sender is None or self._sender.device is not hid_dev:
            self._sender = TelemetrySender(hid_dev)
            self.scheduler.reset()

    def unbind(self) -> None:
        self._sender = None

    def update(self, status: TelemetryStatus) -> bool:
        if not self.enabled or self._sender is None:
            return False
        if not self.scheduler.should_send(status):
            return False
        try:
            self._sender.send(status)
        except TelemetryTransportError as exc:
            logger.warning("Telemetry send failed: %s", exc)
            raise
        # Commit scheduler state only after a successful send.
        self.scheduler.mark_sent(status)
        return True


class StaticFrameController:
    """SLOW PATH: RAM / network / layout only, throttled flash writes.

    Change detection is relative to `_last_committed_state` — the last state
    successfully displayed on screen — so slow drift accumulates instead of
    being swallowed. The baseline only advances after a successful upload.
    """

    def __init__(self, config: Config):
        self.limiter = RefreshLimiter(
            min_interval=config.static_display.min_interval,
            force_interval=config.static_display.force_interval,
        )
        self.detector = StaticChangeDetector(
            thresholds=StaticThresholds(
                memory=config.thresholds.memory,
                cpu=config.thresholds.cpu,
                temperature=config.thresholds.temperature,
            )
        )
        self._last_committed_state: StaticDisplayState | None = None
        self._last_frame_hash: str | None = None
        self._pending_reason = "manual"

    def update(self, state: StaticDisplayState) -> Image.Image | None:
        forced = self.limiter.must_force()
        if not forced and not self.limiter.allow():
            logger.debug("Frame skipped: min interval not reached")
            return None

        changed = self.detector.changed(self._last_committed_state, state)
        if not forced and not changed:
            logger.debug("Frame skipped: no significant change")
            return None

        image = render(state)
        digest = build_frame_buffer(image, NOVA98).sha256
        if not forced and digest == self._last_frame_hash:
            # Screen already shows exactly this content; commit silently.
            self._commit(state, digest)
            logger.info("Frame skipped: identical hash (state committed)")
            return None

        self._pending_reason = "forced" if forced else "changed"
        return image

    def mark_uploaded(self, state: StaticDisplayState) -> None:
        """Commit baseline ONLY after a successful upload."""
        digest = build_frame_buffer(render(state), NOVA98).sha256
        self._commit(state, digest)
        logger.info("Screen updated (%s)", self._pending_reason)

    def _commit(self, state: StaticDisplayState, digest: str) -> None:
        self._last_committed_state = state
        self._last_frame_hash = digest
        self.limiter.mark_updated()


class ScreenRuntime:
    states = ("CONNECTED", "DISCONNECTED", "RECONNECTING", "BACKOFF")

    def __init__(self, config: Config, telemetry_scheduler=None):
        self.config = config
        self.session = DeviceSession()
        self.static = StaticFrameController(config)
        self.telemetry = TelemetryController(
            telemetry_scheduler
            or TelemetryScheduler(
                interval_s=config.telemetry.interval,
                force_interval_s=config.telemetry.force_interval,
                cpu_delta=config.telemetry.thresholds.get("cpu", 1),
                gpu_delta=config.telemetry.thresholds.get("gpu", 1),
                temperature_delta=config.telemetry.thresholds.get("temperature", 1),
            )
        )
        self.telemetry.enabled = config.telemetry.enabled
        self._state = "DISCONNECTED"
        self._backoff_until = 0.0

    @property
    def state(self) -> str:
        return self._state

    def tick(self, metrics: SystemMetrics) -> bool:
        """Run both display channels once. Returns True if a frame was uploaded."""
        if self._state == "BACKOFF":
            if time.monotonic() < self._backoff_until:
                return False
            self._state = "DISCONNECTED"

        if not self.session.ensure_connected():
            self._state = "RECONNECTING"
            return False
        self._state = "CONNECTED"
        if self.telemetry.enabled:
            self.telemetry.bind(self.session.device)

        # FAST PATH first: cheap, frequent.
        uploaded = False
        try:
            self.telemetry.update(metrics_to_telemetry(metrics))
        except (TelemetryTransportError, HidError, OSError) as exc:
            logger.warning("Telemetry channel error: %s", exc)
            self.session.disconnect()
            self.telemetry.unbind()
            self._state = "DISCONNECTED"
            return False

        # SLOW PATH: expensive framebuffer upload, static data only.
        try:
            state = static_display_state(metrics)
            image = self.static.update(state)
            if image is not None:
                uploaded = self._upload_with_retry(state)
        except (HidError, OSError) as exc:
            logger.warning("Static channel error: %s", exc)
            self.session.disconnect()
            self.telemetry.unbind()
            self._state = "DISCONNECTED"
        return uploaded

    def _upload_with_retry(self, state: StaticDisplayState) -> bool:
        from nova98.display.uploader import SafetyError, upload_single_frame

        for attempt in range(1, MAX_UPLOAD_RETRIES + 1):
            try:
                upload_single_frame(render(state), self.session.device)
                self.static.mark_uploaded(state)
                logger.info("Upload attempt %d ok", attempt)
                return True
            except SafetyError:
                logger.exception("Safety limit violated; refusing further uploads")
                self._enter_backoff()
                return False
            except (OSError, HidError) as exc:
                logger.warning("Upload attempt %d failed: %s", attempt, exc)
                time.sleep(1.0)

        logger.error("Upload failed %d times, entering BACKOFF", MAX_UPLOAD_RETRIES)
        self._enter_backoff()
        return False

    def _enter_backoff(self) -> None:
        """Close the HID handle so BACKOFF recovery re-enumerates and reopens."""
        self.telemetry.unbind()
        self.session.disconnect()
        self._state = "BACKOFF"
        self._backoff_until = time.monotonic() + BACKOFF_S

    def shutdown(self) -> None:
        self.telemetry.unbind()
        self.session.disconnect()
