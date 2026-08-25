"""Screen runtime with an active static framebuffer channel and an optional
experimental telemetry channel (disabled by default on NOVA98)."""

from __future__ import annotations

import logging
import time

from PIL import Image

from nova98.config import Config
from nova98.device.hid_device import HidError, Nova98Hid
from nova98.device.profiles import NOVA98
from nova98.display.framebuffer import build_frame_buffer
from nova98.display.prepared import PreparedFrame
from nova98.metrics.base import SystemMetrics
from nova98.renderer.renderer import render
from nova98.renderer.state import StaticDisplayState, static_display_state
from nova98.scheduler.change_detector import StaticChangeDetector, StaticThresholds
from nova98.scheduler.refresh import RefreshLimiter
from nova98.scheduler.stats import StaticUploadStats
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
    """Experimental cmd 52 channel.

    Protocol is valid (55 34 ACK), but NOVA98 firmware currently does not
    render the supplied values. Disabled by default; retained for future
    firmware and other AULA models.
    """

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
    """Active display channel: CPU / CPU temperature / RAM / network rendered
    to a 240x135 framebuffer and uploaded via cmd 80.

    Flash-write safety invariants:
    - Change detection is relative to `_last_committed_state` (the last state
      successfully displayed), so slow drift accumulates instead of being
      swallowed. The baseline only advances after a successful upload.
    - An identical framebuffer is NEVER re-uploaded, even when the force
      interval expires. Force means "re-evaluate", not "rewrite".
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
        self.stats = StaticUploadStats()

    def prepare(self, state: StaticDisplayState) -> PreparedFrame | None:
        """Evaluate a refresh candidate. Renders at most once per call.

        The returned PreparedFrame is the single source for hashing,
        uploading and committing — no re-render ever happens downstream.
        """
        forced = self.limiter.must_force()
        if not forced and not self.limiter.allow():
            logger.debug("Static frame skipped: min interval not reached")
            self.stats.skipped_interval += 1
            return None

        changed = self.detector.changed(self._last_committed_state, state)
        if not forced and not changed:
            logger.debug("Static frame skipped: unchanged state")
            self.stats.skipped_unchanged += 1
            return None

        # Exactly one render per candidate.
        image = render(state)
        digest = build_frame_buffer(image, NOVA98).sha256
        if digest == self._last_frame_hash:
            # Screen already shows exactly this content; commit silently.
            # Applies regardless of force: force re-evaluates, never rewrites.
            self._commit(state, digest)
            self.stats.skipped_hash += 1
            logger.info("Static frame skipped: identical framebuffer hash")
            return None

        self._pending_reason = "forced-evaluation" if forced else "changed"
        return PreparedFrame(
            state=state,
            image=image,
            digest=digest,
            reason=self._pending_reason,
        )

    def mark_uploaded(self, prepared: PreparedFrame) -> None:
        """Commit baseline ONLY after a successful upload of THIS prepared frame."""
        self._commit(prepared.state, prepared.digest)
        self.stats.succeeded += 1
        logger.info(
            "Static frame uploaded: reason=%s total_uploads=%d",
            prepared.reason,
            self.stats.succeeded,
        )

    def mark_failed(self) -> None:
        self.stats.failed += 1

    def _commit(self, state: StaticDisplayState, digest: str) -> None:
        self._last_committed_state = state
        self._last_frame_hash = digest
        self.limiter.mark_updated()

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
        # Experimental channel is not initialized at all when disabled.
        self.telemetry: TelemetryController | None = (
            TelemetryController(
                telemetry_scheduler
                or TelemetryScheduler(
                    interval_s=config.telemetry.interval,
                    force_interval_s=config.telemetry.force_interval,
                    cpu_delta=config.telemetry.thresholds.get("cpu", 1),
                    gpu_delta=config.telemetry.thresholds.get("gpu", 1),
                    temperature_delta=config.telemetry.thresholds.get("temperature", 1),
                )
            )
            if config.telemetry.enabled
            else None
        )
        self._backend = None
        self._state = "DISCONNECTED"
        self._backoff_until = 0.0

    @property
    def state(self) -> str:
        return self._state

    def tick(self, metrics: SystemMetrics) -> bool:
        """Run the active display channel(s) once. True if a frame was uploaded."""
        if self._state == "BACKOFF":
            if time.monotonic() < self._backoff_until:
                return False
            self._state = "DISCONNECTED"

        if not self.session.ensure_connected():
            self._state = "RECONNECTING"
            return False
        self._state = "CONNECTED"
        from nova98.display.backend import FlashFramebufferBackend

        self._backend = FlashFramebufferBackend(self.session.device)

        # Experimental telemetry first: skipped entirely when disabled.
        uploaded = False
        if self.telemetry is not None:
            try:
                self.telemetry.update(metrics_to_telemetry(metrics))
            except (TelemetryTransportError, HidError, OSError) as exc:
                logger.warning("Telemetry channel error: %s", exc)
                self.session.disconnect()
                self.telemetry.unbind()
                self._state = "DISCONNECTED"
                return False

        # Active display path: throttled framebuffer upload.
        try:
            state = static_display_state(metrics)
            prepared = self.static.prepare(state)
            if prepared is not None:
                uploaded = self._upload_with_retry(prepared)
        except (HidError, OSError) as exc:
            logger.warning("Static channel error: %s", exc)
            self.session.disconnect()
            if self.telemetry is not None:
                self.telemetry.unbind()
            self._state = "DISCONNECTED"
        return uploaded

    def _upload_with_retry(self, prepared: PreparedFrame) -> bool:
        from nova98.display.uploader import SafetyError

        for attempt in range(1, MAX_UPLOAD_RETRIES + 1):
            try:
                self._backend.show(prepared.image)
                self.static.mark_uploaded(prepared)
                logger.info("Upload attempt %d ok", attempt)
                return True
            except SafetyError:
                logger.exception("Safety limit violated; refusing further uploads")
                self._enter_backoff()
                return False
            except (OSError, HidError) as exc:
                self.static.stats.failed += 1
                logger.warning("Upload attempt %d failed: %s", attempt, exc)
                time.sleep(1.0)

        logger.error("Upload failed %d times, entering BACKOFF", MAX_UPLOAD_RETRIES)
        self._enter_backoff()
        return False

    def _enter_backoff(self) -> None:
        """Close the HID handle so BACKOFF recovery re-enumerates and reopens."""
        if self.telemetry is not None:
            self.telemetry.unbind()
        self.session.disconnect()
        self._state = "BACKOFF"
        self._backoff_until = time.monotonic() + BACKOFF_S

    def shutdown(self) -> None:
        if self.telemetry is not None:
            self.telemetry.unbind()
        self.session.disconnect()
