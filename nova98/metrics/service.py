"""MetricsService: samples system state. Never touches the screen.

Honours MetricsConfig switches: a disabled metric returns None and its
provider is never created/called. Expensive providers (temperature, GPU)
are wrapped in CachedMetric so they sample at their own slower cadence.
"""

from __future__ import annotations

from datetime import datetime

from nova98.config import MetricsConfig
from nova98.metrics.base import SystemMetrics
from nova98.metrics.cpu import sample as cpu_sample
from nova98.metrics.gpu import GPUProvider, get_platform_gpu_provider
from nova98.metrics.memory import sample as memory_sample
from nova98.metrics.network import NetworkRateCalculator
from nova98.metrics.temperature import TemperatureProvider, get_platform_provider

TEMPERATURE_SAMPLE_INTERVAL_S = 5.0
GPU_SAMPLE_INTERVAL_S = 5.0


class MetricsService:
    def __init__(
        self,
        metrics_config: MetricsConfig | None = None,
        temperature_provider: TemperatureProvider | None = None,
        gpu_provider: GPUProvider | None = None,
    ):
        config = metrics_config or MetricsConfig()

        self._cpu_enabled = config.cpu
        self._memory_enabled = config.memory
        self._network_enabled = config.network

        self._network = NetworkRateCalculator() if config.network else None

        # Disabled providers are never created.
        self._temperature: TemperatureProvider | None = (
            temperature_provider
            if temperature_provider is not None
            else (get_platform_provider() if config.temperature else None)
        )
        self._gpu: GPUProvider | None = (
            gpu_provider
            if gpu_provider is not None
            else (get_platform_gpu_provider() if config.gpu else None)
        )

        from nova98.metrics.cached import CachedMetric

        self._temperature_cache = (
            CachedMetric(self._temperature.get_cpu_temperature, TEMPERATURE_SAMPLE_INTERVAL_S)
            if self._temperature is not None
            else None
        )
        self._gpu_cache = (
            CachedMetric(self._gpu.read, GPU_SAMPLE_INTERVAL_S)
            if self._gpu is not None
            else None
        )

        # Prime psutil counter; first call is meaningless.
        if self._cpu_enabled:
            cpu_sample()

    def read(self) -> SystemMetrics:
        download = upload = None
        if self._network is not None:
            download, upload = self._network.update()

        cpu_temp = self._temperature_cache.get() if self._temperature_cache else None
        gpu_metrics = self._gpu_cache.get() if self._gpu_cache else None

        return SystemMetrics(
            cpu_percent=cpu_sample() if self._cpu_enabled else None,
            memory_percent=memory_sample() if self._memory_enabled else None,
            cpu_temperature=cpu_temp,
            gpu_percent=gpu_metrics.usage if gpu_metrics else None,
            gpu_temperature=gpu_metrics.temperature if gpu_metrics else None,
            download_bytes_per_sec=download,
            upload_bytes_per_sec=upload,
            timestamp=datetime.now(),
        )
