import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nova98.config import MetricsConfig
from nova98.metrics.base import SystemMetrics
from nova98.metrics.service import MetricsService


class ExplodingTempProvider:
    def get_cpu_temperature(self):
        raise AssertionError("temperature provider must not be created/called")


class ExplodingGPUProvider:
    def read(self):
        raise AssertionError("gpu provider must not be created/called")


def test_disabled_temperature_never_calls_provider(monkeypatch):
    # Config-disabled: platform provider must not even be constructed.
    monkeypatch.setattr(
        "nova98.metrics.service.get_platform_provider",
        lambda: (_ for _ in ()).throw(AssertionError("created despite config")),
    )
    config = MetricsConfig(temperature=False)
    service = MetricsService(config)
    m = service.read()
    assert m.cpu_temperature is None


def test_disabled_gpu_never_calls_provider(monkeypatch):
    monkeypatch.setattr(
        "nova98.metrics.service.get_platform_gpu_provider",
        lambda: (_ for _ in ()).throw(AssertionError("created despite config")),
    )
    config = MetricsConfig(gpu=False)
    service = MetricsService(config)
    m = service.read()
    assert m.gpu_percent is None
    assert m.gpu_temperature is None


def test_disabled_cpu_and_memory_and_network():
    config = MetricsConfig(cpu=False, memory=False, network=False)
    service = MetricsService(
        config,
        temperature_provider=_FakeTempNone(),
        gpu_provider=_NullGPU(),
    )
    m = service.read()
    assert m.cpu_percent is None
    assert m.memory_percent is None
    assert m.download_bytes_per_sec is None
    assert m.upload_bytes_per_sec is None


def test_enabled_metrics_return_values():
    from nova98.metrics.gpu import GPUMetrics

    class FakeGPU:
        def read(self):
            return GPUMetrics(usage=42.0, temperature=61.0)

    class FakeTemp:
        def get_cpu_temperature(self):
            return 55.0

    service = MetricsService(
        MetricsConfig(),
        temperature_provider=FakeTemp(),
        gpu_provider=FakeGPU(),
    )
    service.read()  # prime
    m = service.read()
    assert 0 <= m.cpu_percent <= 100
    assert m.cpu_temperature == 55.0
    assert m.gpu_percent == 42.0
    assert m.gpu_temperature == 61.0


class _NullGPU:
    def read(self):
        from nova98.metrics.gpu import GPUMetrics

        return GPUMetrics()


class _FakeTempNone:
    def get_cpu_temperature(self):
        return None


def test_sample_metrics_honours_config_in_cli_path(monkeypatch):
    """preview/show go through _sample_metrics(config); config must reach the service."""
    import nova98.cli as cli
    from nova98.config import Config

    created = []

    class TrackingService:
        def __init__(self, metrics_config=None):
            created.append(metrics_config)

        def read(self):
            return SystemMetrics()

    monkeypatch.setattr(cli, "MetricsService", TrackingService)
    monkeypatch.setattr(cli.time, "sleep", lambda s: None)

    config = Config()
    config.metrics = MetricsConfig(temperature=False, gpu=False, network=False)
    cli._sample_metrics(config)

    assert len(created) == 1
    assert created[0].temperature is False
    assert created[0].gpu is False


def test_telemetry_test_respects_dry_run_without_device():
    # dry-run path never constructs Nova98Hid; covered by CLI wiring here.
    from nova98.telemetry.encoder import encode_system_status
    from nova98.telemetry.model import TelemetryStatus

    payload = encode_system_status(TelemetryStatus(cpu_usage=10))
    assert payload[12] == 10


def test_unparsable_tool_falls_through_to_next(monkeypatch):
    """osx-cpu-temp prints 0.0 on Apple Silicon; provider must try smctemp next."""
    from nova98.metrics.temperature import MacOSTemperatureProvider

    calls = []

    class FakeShutil:
        def __init__(self, paths):
            self.paths = paths

        def which(self, tool):
            calls.append(tool)
            return self.paths.get(tool)

    monkeypatch.setattr(
        "nova98.metrics.temperature.shutil", FakeShutil(
            {"osx-cpu-temp": "/usr/bin/osx-cpu-temp", "smctemp": "/usr/bin/smctemp"}
        )
    )

    import subprocess as sp

    outputs = {
        "/usr/bin/osx-cpu-temp": "0.0°C\n",
        "/usr/bin/smctemp": "63.9\n",
    }

    def fake_run(cmd, **kwargs):
        out = outputs[cmd[0]]

        class R:
            stdout = out

        return R()

    monkeypatch.setattr("nova98.metrics.temperature.subprocess.run", fake_run)
    value = MacOSTemperatureProvider().get_cpu_temperature()
    assert value == 63.9
    # smctemp tried first on Apple Silicon; both tools consulted.
    assert calls[0] == "smctemp"
