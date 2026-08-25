import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nova98.metrics.base import SystemMetrics
from nova98.scheduler.telemetry import TelemetryScheduler
from nova98.telemetry.mapper import metrics_to_telemetry
from nova98.telemetry.model import TelemetryStatus


def metrics(**kw) -> SystemMetrics:
    return SystemMetrics(**kw)


def test_mapping_rounds_and_clamps():
    status = metrics_to_telemetry(
        metrics(cpu_percent=47.4, cpu_temperature=55.6, gpu_percent=-3, gpu_temperature=200)
    )
    assert status.cpu_usage == 47
    assert status.cpu_temperature == 56
    assert status.gpu_usage == 0      # clamped low
    assert status.gpu_temperature == 127  # clamped high


def test_mapping_none_passthrough():
    assert metrics_to_telemetry(metrics()) == TelemetryStatus()


def test_first_send_always():
    scheduler = TelemetryScheduler()
    assert scheduler.should_send(TelemetryStatus(cpu_usage=50)) is True
    scheduler.mark_sent(TelemetryStatus(cpu_usage=50))


def test_interval_enforced_even_on_change(monkeypatch):
    scheduler = TelemetryScheduler(interval_s=1.0, force_interval_s=100.0)
    clock = {"t": 0.0}
    monkeypatch.setattr("nova98.scheduler.telemetry.time.monotonic", lambda: clock["t"])

    assert scheduler.should_send(TelemetryStatus(cpu_usage=10)) is True
    scheduler.mark_sent(TelemetryStatus(cpu_usage=10))

    clock["t"] += 0.5  # inside interval even though CPU changed a lot
    assert scheduler.should_send(TelemetryStatus(cpu_usage=90)) is False

    clock["t"] += 0.6  # interval passed: change sends again
    assert scheduler.should_send(TelemetryStatus(cpu_usage=90)) is True


def test_force_interval_forces_even_without_change(monkeypatch):
    scheduler = TelemetryScheduler(interval_s=1.0, force_interval_s=5.0)
    clock = {"t": 0.0}
    monkeypatch.setattr("nova98.scheduler.telemetry.time.monotonic", lambda: clock["t"])

    scheduler.mark_sent(TelemetryStatus(cpu_usage=50))

    clock["t"] += 2.0
    assert scheduler.should_send(TelemetryStatus(cpu_usage=50)) is False

    clock["t"] += 4.0  # total 6s >= force_interval
    assert scheduler.should_send(TelemetryStatus(cpu_usage=50)) is True


def test_failed_send_does_not_commit_state(monkeypatch):
    """If mark_sent is never called, the committed baseline must not advance."""
    scheduler = TelemetryScheduler(interval_s=1.0, force_interval_s=100.0)
    clock = {"t": 0.0}
    monkeypatch.setattr("nova98.scheduler.telemetry.time.monotonic", lambda: clock["t"])

    scheduler.mark_sent(TelemetryStatus(cpu_usage=50))

    clock["t"] += 2.0
    # would-send decision succeeds...
    assert scheduler.should_send(TelemetryStatus(cpu_usage=51)) is True
    # ...but the HID send FAILS -> caller does NOT call mark_sent.
    # Committed baseline must still be cpu=50.
    clock["t"] += 2.0
    assert scheduler.should_send(TelemetryStatus(cpu_usage=50)) is False  # unchanged vs 50
    assert scheduler.should_send(TelemetryStatus(cpu_usage=52)) is True   # +2 >= delta vs 50


def test_invalid_intervals_rejected():
    with pytest.raises(ValueError):
        TelemetryScheduler(interval_s=0)
    with pytest.raises(ValueError):
        TelemetryScheduler(interval_s=5.0, force_interval_s=1.0)


def test_none_appearing_counts_as_change(monkeypatch):
    scheduler = TelemetryScheduler(interval_s=1.0, force_interval_s=100.0)
    clock = {"t": 0.0}
    monkeypatch.setattr("nova98.scheduler.telemetry.time.monotonic", lambda: clock["t"])
    scheduler.mark_sent(TelemetryStatus(cpu_usage=50))
    clock["t"] += 2.0
    assert scheduler.should_send(TelemetryStatus(gpu_temperature=None)) is True
