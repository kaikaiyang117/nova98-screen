import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nova98.telemetry.encoder import encode_system_status
from nova98.telemetry.model import TelemetryStatus
from nova98.telemetry.sender import TelemetrySender, TelemetryTransportError


class RecordingHid:
    def __init__(self, fail: bool = False):
        self.calls: list[bytes] = []
        self.fail = fail

    def send_temporary_data(self, payload: bytes, max_retries: int = 0):
        if self.fail:
            raise OSError("wire gone")
        self.calls.append(payload)
        return [b"\x00" * 24]


def test_sender_encodes_and_forwards():
    hid = RecordingHid()
    sender = TelemetrySender(hid)  # type: ignore[arg-type]
    sender.send(TelemetryStatus(cpu_usage=42, cpu_temperature=55))

    assert len(hid.calls) == 1
    assert hid.calls[0] == encode_system_status(TelemetryStatus(cpu_usage=42, cpu_temperature=55))
    assert hid.calls[0][6] == 0x5A


def test_sender_wraps_transport_errors():
    sender = TelemetrySender(RecordingHid(fail=True))  # type: ignore[arg-type]
    with pytest.raises(TelemetryTransportError):
        sender.send(TelemetryStatus(cpu_usage=1))


def test_sender_rejects_invalid_status_without_touching_hid():
    hid = RecordingHid()
    sender = TelemetrySender(hid)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        sender.send(TelemetryStatus(cpu_usage=200))
    assert hid.calls == []
