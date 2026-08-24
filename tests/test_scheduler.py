import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nova98.config import Config
from nova98.metrics.base import SystemMetrics
from nova98.scheduler.change_detector import ChangeDetector, Thresholds
from nova98.scheduler.refresh import RefreshLimiter


def metrics(**kw) -> SystemMetrics:
    defaults = dict(
        cpu_percent=50.0,
        memory_percent=60.0,
        cpu_temperature=55.0,
        download_bytes_per_sec=100_000.0,
        upload_bytes_per_sec=50_000.0,
        timestamp=datetime.now(),
    )
    defaults.update(kw)
    return SystemMetrics(**defaults)


def feed(detector: ChangeDetector, **kw) -> bool:
    kw.setdefault("timestamp", datetime(2026, 1, 1, 12, 0, 0))
    return detector.significant_change(metrics(**kw))


def test_change_detector_first_call_always_changes():
    detector = ChangeDetector()
    assert feed(detector) is True


def test_change_detector_thresholds():
    detector = ChangeDetector(thresholds=Thresholds(cpu=10, memory=5, temperature=3))
    assert feed(detector, cpu_percent=55.0) is True  # initial

    # Carry-forward state so only one field moves at a time.
    state: dict = {}
    def step(**kw) -> bool:
        state.update(kw)
        return feed(detector, **state)

    assert step(cpu_percent=63.0) is False   # +8 < 10
    assert step(cpu_percent=74.0) is True    # +11 >= 10
    assert step(memory_percent=64.0) is False
    assert step(memory_percent=70.0) is True
    assert step(cpu_temperature=57.5) is False
    assert step(cpu_temperature=61.0) is True
    # None appearing/disappearing counts as change.
    assert step(cpu_temperature=None) is True
    assert step(cpu_temperature=60.0) is True


def test_network_tier_and_minute_triggers():
    detector = ChangeDetector()
    assert feed(detector, download_bytes_per_sec=100_000.0) is True
    assert feed(detector, download_bytes_per_sec=300_000.0) is False
    assert feed(detector, download_bytes_per_sec=700_000.0) is True
    future = metrics(timestamp=datetime.now() + timedelta(minutes=2), download_bytes_per_sec=700_000.0)
    assert detector.significant_change(future) is True


def test_refresh_limiter_intervals():
    limiter = RefreshLimiter(min_interval=30, force_interval=300)
    assert limiter.allow() and limiter.must_force()  # never updated yet

    limiter.mark_updated()
    assert not limiter.allow()
    assert not limiter.must_force()

    limiter._last_update -= 31  # simulate elapsed time
    assert limiter.allow()
    assert not limiter.must_force()

    limiter._last_update -= 300
    assert limiter.must_force()


def test_config_parser(tmp_path):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(
        """
display:
  refresh:
    min_interval: 45
    force_interval: 600
metrics:
  cpu: true
  temperature: false
thresholds:
  cpu: 15
layout:
  name: compact
"""
    )
    config = Config.load(cfg_file)
    assert config.refresh.min_interval == 45
    assert config.refresh.force_interval == 600
    assert config.metrics.temperature is False
    assert config.thresholds.cpu == 15
    assert config.layout.name == "compact"


def test_config_defaults_when_missing(tmp_path):
    config = Config.load(tmp_path / "nonexistent.yaml")
    assert config.refresh.min_interval == 30
    assert config.thresholds.memory == 5
