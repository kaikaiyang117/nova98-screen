import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nova98.config import Config
from nova98.renderer.state import StaticDisplayState
from nova98.scheduler.change_detector import StaticChangeDetector, StaticThresholds

def _commit(controller, st):
    """prepare + assert + successful upload commit."""
    prepared = controller.prepare(st)
    assert prepared is not None
    controller.mark_uploaded(prepared)



def state(**kw) -> StaticDisplayState:
    defaults = dict(
        memory_percent=60.0,
        download_bytes_per_sec=100_000.0,
        upload_bytes_per_sec=50_000.0,
    )
    defaults.update(kw)
    return StaticDisplayState(**defaults)


def test_first_comparison_always_changed():
    detector = StaticChangeDetector()
    assert detector.changed(None, state()) is True


def test_only_static_fields_detected():
    detector = StaticChangeDetector()
    assert detector.changed(state(memory_percent=50), state(memory_percent=50)) is False


def test_memory_threshold_relative_to_committed():
    detector = StaticChangeDetector(thresholds=StaticThresholds(memory=5.0))
    committed = state(memory_percent=50)
    assert detector.changed(committed, state(memory_percent=54)) is False
    # Drift: still relative to committed 50, not the previous sample.
    assert detector.changed(committed, state(memory_percent=58)) is True
    assert detector.changed(committed, state(memory_percent=45)) is True
    assert detector.changed(committed, state(memory_percent=46)) is False


def test_none_appearing_counts_as_change():
    detector = StaticChangeDetector()
    assert detector.changed(state(memory_percent=50), state(memory_percent=None)) is True
    assert detector.changed(state(memory_percent=None), state(memory_percent=50)) is True


def test_network_tiers():
    detector = StaticChangeDetector()
    committed = state(download_bytes_per_sec=100_000.0)
    assert detector.changed(committed, state(download_bytes_per_sec=300_000.0)) is False
    assert detector.changed(committed, state(download_bytes_per_sec=700_000.0)) is True


# --- StaticFrameController integration --------------------------------------


def make_controller(monkeypatch, min_interval=30.0, force_interval=300.0):
    from nova98.scheduler.runtime import StaticFrameController

    config = Config()
    config.refresh = type(config.refresh)(min_interval=min_interval, force_interval=force_interval)
    controller = StaticFrameController(config)

    clock = {"t": 1000.0}
    monkeypatch.setattr("nova98.scheduler.runtime.time.monotonic", lambda: clock["t"])
    return controller, clock


def test_cpu_change_triggers_static_frame_after_interval(monkeypatch):
    # cmd 52 telemetry renders nothing on NOVA98 firmware, so CPU rides the
    # static channel again and must be change-detected.
    controller, clock = make_controller(monkeypatch, min_interval=30.0)
    displayed = state(cpu_percent=50.0)
    assert controller.prepare(displayed) is not None
    _commit(controller, displayed)

    clock["t"] += 31
    assert controller.prepare(state(cpu_percent=55.0)) is None   # +5 < threshold 10
    assert controller.prepare(state(cpu_percent=65.0)) is not None  # vs committed 50


def test_minute_change_does_not_trigger_static_frame(monkeypatch):
    controller, _ = make_controller(monkeypatch)
    first = controller.prepare(state())
    assert first is not None
    _commit(controller, state())
    # No minute_key trigger exists in the static path anymore.
    assert controller.prepare(state()) is None  # inside min interval


def test_slow_drift_uses_last_committed_baseline(monkeypatch):
    controller, clock = make_controller(monkeypatch, min_interval=30.0)

    displayed = state(memory_percent=50.0)
    image = controller.prepare(displayed)
    assert image is not None
    _commit(controller, displayed)

    clock["t"] += 31
    # Threshold 5, judged against displayed 50 (not previous samples):
    assert controller.prepare(state(memory_percent=54.0)) is None   # 50 -> 54: <5
    assert controller.prepare(state(memory_percent=58.0)) is not None  # 50 -> 58: >=5


def test_failed_upload_does_not_commit_baseline(monkeypatch):
    controller, clock = make_controller(monkeypatch, min_interval=30.0)

    displayed = state(memory_percent=50.0)
    assert controller.prepare(displayed) is not None
    _commit(controller, displayed)

    clock["t"] += 31
    candidate = state(memory_percent=80.0)
    assert controller.prepare(candidate) is not None
    # Upload FAILS -> mark_uploaded never called -> baseline must stay at 50.
    clock["t"] += 31
    # Baseline must still be 50 (failed upload did not commit 80):
    # 53 would be "no change" if baseline had wrongly advanced to 80.
    assert controller.prepare(state(memory_percent=78.0)) is not None


def test_force_does_not_rewrite_identical_frame(monkeypatch):
    """Force interval expiry must NEVER re-upload an identical framebuffer."""
    controller, clock = make_controller(monkeypatch, min_interval=30.0, force_interval=300.0)

    displayed = state()
    assert controller.prepare(displayed) is not None
    _commit(controller, displayed)

    clock["t"] += 301  # force interval long expired
    # Identical state -> identical hash -> no upload, even though forced.
    assert controller.prepare(state()) is None
    assert controller.stats.skipped_hash == 1
    assert controller.stats.frames_succeeded == 1  # only the initial upload


def test_force_uploads_when_frame_actually_changed(monkeypatch):
    controller, clock = make_controller(monkeypatch, min_interval=30.0, force_interval=300.0)

    displayed = state(memory_percent=50.0)
    assert controller.prepare(displayed) is not None
    _commit(controller, displayed)

    clock["t"] += 331  # min + force both expired
    candidate = state(memory_percent=53.0)
    result = controller.prepare(candidate)
    assert result is not None
    _commit(controller, candidate)
    assert controller._last_committed_state.memory_percent == 53.0



def test_temperature_slow_drift_accumulates(monkeypatch):
    controller, clock = make_controller(monkeypatch, min_interval=30.0)
    displayed = state(cpu_temperature=50.0)
    assert controller.prepare(displayed) is not None
    _commit(controller, displayed)

    clock["t"] += 31
    # threshold 3, judged against displayed 50 (not the previous sample):
    assert controller.prepare(state(cpu_temperature=52.0)) is None   # +2 < 3
    assert controller.prepare(state(cpu_temperature=54.0)) is not None  # +4 >= 3


def test_network_tier_judged_against_committed_state(monkeypatch):
    controller, clock = make_controller(monkeypatch, min_interval=30.0)
    committed = state(download_bytes_per_sec=100_000.0)  # tier 0
    assert controller.prepare(committed) is not None
    _commit(controller, committed)

    clock["t"] += 31
    # Previous-sample style detection would compare 300k vs 700k (same tier);
    # correct behaviour compares each against committed 100k (tier 0).
    assert controller.prepare(state(download_bytes_per_sec=700_000.0)) is not None  # tier 1


def test_upload_failure_keeps_stats_consistent(monkeypatch):
    controller, clock = make_controller(monkeypatch, min_interval=30.0)
    displayed = state(memory_percent=50.0)
    assert controller.prepare(displayed) is not None
    _commit(controller, displayed)

    clock["t"] += 31
    candidate = state(memory_percent=90.0)
    assert controller.prepare(candidate) is not None
    # Simulate failure: no mark_uploaded call.
    clock["t"] += 31
    # Baseline still 50 -> 53 is below threshold and stays skipped.
    assert controller.prepare(state(memory_percent=53.0)) is None
    assert controller.stats.frames_succeeded == 1
    # No real wire attempts happened in this unit test (backend faked).
    assert controller.stats.wire_attempts == 0


def test_config_validation_rejects_bad_values(tmp_path):
    import pytest

    from nova98.config import Config

    cases = [
        "display:\n  refresh:\n    min_interval: -1\n",
        "display:\n  refresh:\n    min_interval: 300\n    force_interval: 60\n",
        "telemetry:\n  interval: 0\n",
        "telemetry:\n  interval: 5\n  force_interval: 1\n",
        "thresholds:\n  cpu: -5\n",
    ]
    for i, content in enumerate(cases):
        cfg = tmp_path / f"bad{i}.yaml"
        cfg.write_text(content)
        with pytest.raises(ValueError):
            Config.load(cfg)


def test_config_validation_accepts_valid_file(tmp_path):
    from nova98.config import Config

    cfg = tmp_path / "ok.yaml"
    cfg.write_text(
        "display:\n  refresh:\n    min_interval: 60\n    force_interval: 1800\n"
    )
    config = Config.load(cfg)  # must not raise
    assert config.refresh.min_interval == 60


# --- Config default unification (v0.1.0) -------------------------------------


def test_missing_config_uses_dataclass_defaults(tmp_path):
    from nova98.config import Config

    config = Config.load(tmp_path / "nonexistent.yaml")
    assert config.refresh.min_interval == 60
    assert config.refresh.force_interval == 1800
    assert config.metrics.gpu is False
    assert config.telemetry.enabled is False


def test_empty_yaml_gets_full_defaults(tmp_path):
    from nova98.config import Config

    cfg = tmp_path / "empty.yaml"
    cfg.write_text("{}\n")
    config = Config.load(cfg)
    assert config == Config()


def test_partial_metrics_config_preserves_defaults(tmp_path):
    from nova98.config import Config

    cfg = tmp_path / "partial.yaml"
    cfg.write_text("metrics:\n  cpu: false\n")
    m = Config.load(cfg).metrics
    assert m.cpu is False
    assert m.memory is True
    assert m.temperature is True
    assert m.gpu is False
    assert m.network is True


def test_partial_refresh_preserves_force_default(tmp_path):
    from nova98.config import Config

    cfg = tmp_path / "refresh.yaml"
    cfg.write_text("display:\n  refresh:\n    min_interval: 120\n")
    r = Config.load(cfg).refresh
    assert r.min_interval == 120
    assert r.force_interval == 1800


def test_metrics_sample_interval_independent_of_telemetry(tmp_path):
    from nova98.config import Config

    cfg = tmp_path / "cadence.yaml"
    cfg.write_text(
        "metrics:\n"
        "  sample_interval: 2.5\n"
        "telemetry:\n"
        "  interval: 99\n"
        "  force_interval: 200\n"
        "  enabled: false\n"
    )
    config = Config.load(cfg)
    assert config.metrics.sample_interval == 2.5
    assert config.telemetry.interval == 99      # unrelated field
    assert config.telemetry.enabled is False


def test_metrics_sample_interval_validated(tmp_path):
    import pytest

    from nova98.config import Config

    cfg = tmp_path / "bad.yaml"
    cfg.write_text("metrics:\n  sample_interval: 0\n")
    with pytest.raises(ValueError):
        Config.load(cfg)
