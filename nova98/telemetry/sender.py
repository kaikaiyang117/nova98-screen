"""TelemetrySender: TelemetryStatus -> encoder -> Nova98Hid cmd 52."""

from __future__ import annotations

import logging

from nova98.device.hid_device import Nova98Hid
from nova98.telemetry.encoder import encode_system_status
from nova98.telemetry.model import TelemetryStatus

logger = logging.getLogger(__name__)


class TelemetryTransportError(IOError):
    """cmd 52 transport failure. Low-risk temporary command, not a flash write."""


class TelemetrySender:
    def __init__(self, hid_device: Nova98Hid):
        self._hid = hid_device

    @property
    def device(self) -> Nova98Hid:
        """Read-only access to the bound HID device (identity checks)."""
        return self._hid

    def send(self, status: TelemetryStatus) -> None:
        payload = encode_system_status(status)
        try:
            self._hid.send_temporary_data(payload)
        except (IOError, OSError) as exc:
            raise TelemetryTransportError(f"telemetry send failed: {exc}") from exc
        logger.debug("Telemetry sent: %s", status)
