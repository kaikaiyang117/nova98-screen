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

def _commit(controller, st):
    """prepare + assert + successful upload commit."""
    prepared = controller.prepare(st)
    assert prepared is not None
    controller.mark_uploaded(prepared)



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
    from nova98.renderer.state import StaticDisplayState

    controller = StaticFrameController(Config())
    clock = {"t": 1000.0}
    monkeypatch.setattr("nova98.scheduler.runtime.time.monotonic", lambda: clock["t"])

    def state(ram):
        return StaticDisplayState(memory_percent=ram)

    first = controller.prepare(state(50))
    assert first is not None  # forced initial render
    _commit(controller, state(50))

    # Inside min interval: nothing.
    assert controller.prepare(state(90)) is None

    clock["t"] += 61
    # Outside interval but below change threshold (5): no update.
    assert controller.prepare(state(53)) is None
    # Big jump vs committed 50: renders again.
    assert controller.prepare(state(90)) is not None


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


def test_runtime_disabled_telemetry_not_initialized():
    config = Config()
    config.telemetry.enabled = False
    runtime = ScreenRuntime(config)
    assert runtime.telemetry is None


def test_runtime_enabled_telemetry_is_initialized():
    config = Config()
    config.telemetry.enabled = True
    runtime = ScreenRuntime(config)
    assert runtime.telemetry is not None


def test_runtime_telemetry_refusing_send_disconnects(monkeypatch):
    """A telemetry transport error must tear down the session, not crash."""
    from nova98.telemetry.sender import TelemetryTransportError

    config = Config()
    config.telemetry.enabled = True
    runtime = ScreenRuntime(config)
    runtime.telemetry.update = lambda status: (_ for _ in ()).throw(
        TelemetryTransportError("gone")
    )

    disconnects = []

    class FakeHid:
        profile = None

        def close(self):
            pass

    monkeypatch.setattr(runtime.session, "_hid", FakeHid())
    monkeypatch.setattr(runtime.session, "ensure_connected", lambda: True)
    monkeypatch.setattr(runtime.session, "disconnect", lambda: disconnects.append(1))
    monkeypatch.setattr(runtime, "_upload_with_retry", lambda state: False)

    metrics = SystemMetrics(cpu_percent=50, timestamp=datetime(2026, 1, 1))
    assert runtime.tick(metrics) is False
    assert runtime.state == "DISCONNECTED"
    assert disconnects == [1]


def test_backoff_closes_and_reopens_hid(monkeypatch):
    import time as time_mod

    from nova98.scheduler.runtime import BACKOFF_S

    runtime = ScreenRuntime(Config())
    opened: list[int] = []
    closed: list[int] = []

    class FakeHidDev:
        def close(self):
            closed.append(1)

    monkeypatch.setattr(
        "nova98.display.uploader.upload_single_frame",
        lambda image, dev: (_ for _ in ()).throw(OSError("wire gone")),
    )

    # Force a failing upload into backoff.
    monkeypatch.setattr(runtime.session, "_hid", FakeHidDev())
    from nova98.display.uploader import UploadResult

    class FailingBackend:
        def show(self, image):
            raise OSError("wire gone")

    runtime._backend = FailingBackend()
    sleeps = []
    monkeypatch.setattr("nova98.scheduler.runtime.time.sleep", lambda s: sleeps.append(s))

    from nova98.renderer.state import StaticDisplayState
    from datetime import datetime

    from nova98.display.prepared import PreparedFrame
    from nova98.renderer.renderer import render as _render

    st = StaticDisplayState(memory_percent=10.0)
    image = _render(st)
    prepared = PreparedFrame(
        state=st,
        image=image,
        digest="deadbeef",
        reason="changed",
    )
    assert runtime._upload_with_retry(prepared) is False

    assert runtime.state == "BACKOFF"
    assert not runtime.session.connected  # handle released, will re-enumerate
    assert runtime.static.stats.wire_failures == 3


def test_backoff_exits_via_reconnect(monkeypatch):
    import types

    class FakeBackend:
        def __init__(self, hid):
            self.hid = hid

        def show(self, image):
            return types.SimpleNamespace(pages=16, acks=16, duration_s=1.0)

    runtime = ScreenRuntime(Config(), backend_factory=FakeBackend)
    assert runtime.telemetry is None  # disabled by default: never initialized

    class IdleHid:
        def close(self):
            pass

    monkeypatch.setattr(runtime.session, "_hid", IdleHid())

    class SuccessBackendUnused:
        def show(self, image):
            self.shown = image
            return types.SimpleNamespace(pages=16, acks=16, duration_s=1.0)

    connect_attempts = {"n": 0}

    def fake_ensure():
        connect_attempts["n"] += 1
        return connect_attempts["n"] > 1

    monkeypatch.setattr(runtime.session, "ensure_connected", fake_ensure)

    clock = {"t": 0.0}
    monkeypatch.setattr("nova98.scheduler.runtime.time.monotonic", lambda: clock["t"])

    # Simulate entering backoff now.
    runtime._state = "BACKOFF"
    runtime._backoff_until = clock["t"] + 60.0

    metrics = SystemMetrics(timestamp=datetime(2026, 1, 1))
    # Still in backoff window.
    assert runtime.tick(metrics) is False
    clock["t"] += 61.0
    # Backoff expired: reconnect path runs again (attempt 1 fails).
    assert runtime.tick(metrics) is False
    assert runtime.state == "RECONNECTING"
    assert connect_attempts["n"] == 1
    # Attempt 2 connects; forced initial static frame uploads.
    assert runtime.tick(metrics) is True
    assert runtime.state == "CONNECTED"
    assert connect_attempts["n"] == 2
