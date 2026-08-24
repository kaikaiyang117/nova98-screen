import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nova98.metrics.base import SystemMetrics
from nova98.telemetry.mapper import metrics_to_telemetry
from nova98.telemetry.model import TelemetryStatus
from nova98.scheduler.telemetry import TelemetryScheduler


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
    status = metrics_to_telemetry(metrics())
    assert status == TelemetryStatus()


def test_scheduler_first_send_always():
    scheduler = TelemetryScheduler()
    assert scheduler.should_send(TelemetryStatus(cpu_usage=50)) is True


def test_scheduler_delta_thresholds():
    scheduler = TelemetryScheduler(interval_s=1.0)
    scheduler.mark_sent()
    assert scheduler.should_send(TelemetryStatus(cpu_usage=50)) is True  # first

    scheduler.mark_sent()
    assert scheduler.should_send(TelemetryStatus(cpu_usage=50)) is False  # identical
    assert scheduler.should_send(TelemetryStatus(cpu_usage=51)) is True   # +1 >= delta

    scheduler.mark_sent()
    assert scheduler.should_send(TelemetryStatus(gpu_temperature=None)) is True  # None appears


def test_scheduler_force_interval(monkeypatch):
    scheduler = TelemetryScheduler(force_interval_s=5.0)
    assert scheduler.should_send(TelemetryStatus(cpu_usage=10)) is True

    clock = {"t": 100.0}
    monkeypatch.setattr("nova98.scheduler.telemetry.time.monotonic", lambda: clock["t"])
    scheduler.mark_sent()

    clock["t"] += 2.0
    assert scheduler.should_send(TelemetryStatus(cpu_usage=10)) is False  # same value, inside force window

    clock["t"] += 3.1
    assert scheduler.should_send(TelemetryStatus(cpu_usage=10)) is True   # forced after 5s
