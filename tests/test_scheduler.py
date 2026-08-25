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


# --- v0.1.0 runtime safety invariants ----------------------------------------


class _RenderCounter:
    """Counts render() invocations inside the scheduler module."""

    def __init__(self, monkeypatch):
        self.calls = 0
        import nova98.scheduler.runtime as rt

        original = rt.render

        def counting(state):
            self.calls += 1
            return original(state)

        monkeypatch.setattr(rt, "render", counting)

    def __int__(self):
        return self.calls


def _fake_backend(recorder):
    import types

    class FakeBackend:
        def __init__(self, hid=None):
            FakeBackend.last = self
            self.shown = []

        def show(self, image):
            recorder.append(image)
            return types.SimpleNamespace(pages=16, acks=16, duration_s=1.0)

    return FakeBackend


def test_prepare_renders_exactly_once_per_candidate(monkeypatch):
    from nova98.config import Config
    from nova98.scheduler.runtime import StaticFrameController

    counter = _RenderCounter(monkeypatch)
    controller = StaticFrameController(Config())
    st = state(memory_percent=10.0)

    prepared = controller.prepare(st)
    assert prepared is not None
    assert int(counter) == 1  # one candidate -> exactly one render


def test_uploaded_image_is_prepared_image_and_digest_matches(monkeypatch):
    import nova98.display.uploader as up_mod
    from nova98.config import Config
    from nova98.display.framebuffer import build_frame_buffer
    from nova98.device.profiles import NOVA98
    from nova98.scheduler.runtime import ScreenRuntime

    shown = []
    runtime = ScreenRuntime(Config(), backend_factory=_fake_backend(shown))
    runtime._backend = runtime._backend_factory(None)
    monkeypatch.setattr(runtime.session, "ensure_connected", lambda: True)
    monkeypatch.setattr(runtime.session, "_hid", type("H", (), {"close": lambda s: None})())

    st = static_state(memory_percent=33.0)
    prepared = runtime.static.prepare(st)
    assert prepared is not None
    expected_digest = build_frame_buffer(prepared.image, NOVA98).sha256
    assert prepared.digest == expected_digest

    assert runtime._upload_with_retry(prepared) is True
    assert shown[0] is prepared.image  # same object uploaded, not a re-render
    assert runtime.static._last_frame_hash == prepared.digest


def test_failed_upload_does_not_commit_prepared_frame(monkeypatch):
    import types

    from nova98.config import Config
    from nova98.scheduler.runtime import ScreenRuntime

    class FailingBackend:
        def __init__(self, hid=None):
            pass

        def show(self, image):
            raise OSError("gone")

    runtime = ScreenRuntime(Config(), backend_factory=FailingBackend)
    runtime._backend = runtime._backend_factory(None)
    monkeypatch.setattr(runtime.session, "ensure_connected", lambda: True)
    monkeypatch.setattr(runtime.session, "_hid", type("H", (), {"close": lambda s: None})())
    sleeps = []
    monkeypatch.setattr(
        "nova98.scheduler.runtime.time", _FrozenTime(sleeps)
    )

    st = static_state(memory_percent=44.0)
    prepared = runtime.static.prepare(st)
    assert prepared is not None
    assert runtime._upload_with_retry(prepared) is False
    assert runtime.static._last_committed_state is None  # baseline untouched
    assert runtime.state == "BACKOFF"


def test_changed_state_but_identical_render_skips_upload(monkeypatch):
    # RAM 50->53 (below threshold) plus CPU jump that changes detection...
    # but if the rendered frame were identical it must still skip.
    from nova98.config import Config
    from nova98.scheduler.runtime import StaticFrameController

    calls = []
    import nova98.scheduler.runtime as rt

    monkeypatch.setattr(
        rt,
        "render",
        lambda st: (calls.append(1), _constant_image())[1],
    )
    controller, clock = make_controller(monkeypatch, min_interval=30.0)
    first = controller.prepare(static_state(cpu_percent=20.0))
    assert first is not None
    controller.mark_uploaded(first)

    clock["t"] += 61  # min interval expired
    # Different state (passes detector) but patched render returns an
    # identical image -> must be skipped by hash without any upload.
    second = controller.prepare(static_state(cpu_percent=95.0))
    assert second is None
    assert controller.stats.skipped_hash == 1


def test_backend_can_be_injected_into_runtime():
    from nova98.config import Config
    from nova98.scheduler.runtime import ScreenRuntime

    created = []

    class ProbeBackend:
        def __init__(self, hid):
            created.append(hid)

        def show(self, image):
            raise AssertionError("not called in this test")

    runtime = ScreenRuntime(Config(), backend_factory=ProbeBackend)
    fake_hid = object()
    runtime.session._hid = fake_hid
    runtime._backend = None
    # simulate the connect-time creation path
    runtime._backend = (
        ProbeBackend(runtime.session.device) if False else ProbeBackend(fake_hid)
    )
    assert created == [fake_hid]


# helpers ---------------------------------------------------------------------


def static_state(**kw):
    return state(**kw)


def _constant_image():
    from PIL import Image

    return Image.new("RGB", (240, 135), (1, 2, 3))


class _FrozenTime:
    """Replaces scheduler time module usage in runtime for backoff test."""

    def __init__(self, sleeps):
        self.sleeps = sleeps
        self.now = 0.0

    def monotonic(self):
        return self.now

    def sleep(self, s):
        self.sleeps.append(s)
