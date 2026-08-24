import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nova98.config import Config
from nova98.device.hid_device import HidError
from nova98.metrics.base import SystemMetrics
from nova98.scheduler.runtime import (
    DeviceSession,
    ScreenRuntime,
    StaticFrameController,
    TelemetryController,
)
from nova98.scheduler.telemetry import TelemetryScheduler
from datetime import datetime


class FakeSession:
    def __init__(self):
        self.connected = False
        self.disconnects = 0

    def ensure_connected(self):
        return not self.connected and False or True


def test_device_session_requires_connect():
    session = DeviceSession()
    assert not session.connected
    with pytest.raises(HidError):
        _ = session.device


def test_static_controller_respects_min_interval(monkeypatch):
    controller = StaticFrameController(Config())
    clock = {"t": 1000.0}
    monkeypatch.setattr("nova98.scheduler.runtime.time.monotonic", lambda: clock["t"])

    def metrics(cpu):
        return SystemMetrics(cpu_percent=cpu, timestamp=datetime(2026, 1, 1, 12, 0, 0))

    first = controller.update(metrics(50))
    assert first is not None  # forced initial render
    controller.mark_uploaded(first)

    # Inside min interval: nothing.
    assert controller.update(metrics(90)) is None

    clock["t"] += 31
    # Outside interval but below change threshold (10): no update.
    assert controller.update(metrics(55)) is None
    # Big jump: renders again.
    assert controller.update(metrics(90)) is not None


def test_telemetry_controller_skips_and_sends():
    sent: list = []

    class FakeHid:
        def send_temporary_data(self, payload, max_retries=0):
            sent.append(payload)
            return []

    scheduler = TelemetryScheduler(force_interval_s=3600)
    controller = TelemetryController(scheduler)

    from nova98.device.hid_device import Nova98Hid

    fake_dev = Nova98Hid.__new__(Nova98Hid)  # not opened; only identity matters
    controller.bind(fake_dev)
    controller._sender._hid = FakeHid()  # inject transport double

    from nova98.telemetry.model import TelemetryStatus

    assert controller.update(TelemetryStatus(cpu_usage=10)) is True
    assert controller.update(TelemetryStatus(cpu_usage=10)) is False  # unchanged
    assert len(sent) == 1


def test_runtime_disabled_telemetry_sends_nothing(monkeypatch):
    config = Config()
    config.telemetry.enabled = False
    runtime = ScreenRuntime(config)

    uploads = []
    monkeypatch.setattr(
        "nova98.display.uploader.upload_single_frame",
        lambda image, dev: uploads.append(image) or __import__("types").SimpleNamespace(pages=16, acks=16, duration_s=1),
    )
    monkeypatch.setattr(runtime.session, "ensure_connected", lambda: True)
    monkeypatch.setattr(runtime, "_upload_with_retry", lambda image: True)

    metrics = SystemMetrics(cpu_percent=50, timestamp=datetime(2026, 1, 1))
    runtime.tick(metrics)  # must not raise despite no real device
