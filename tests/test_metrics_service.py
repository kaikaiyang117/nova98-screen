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
