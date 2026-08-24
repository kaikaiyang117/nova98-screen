"""MetricsService: samples system state. Never touches the screen."""

from __future__ import annotations

from datetime import datetime

from nova98.metrics.base import SystemMetrics
from nova98.metrics.cpu import sample as cpu_sample
from nova98.metrics.gpu import GPUProvider, get_platform_gpu_provider
from nova98.metrics.memory import sample as memory_sample
from nova98.metrics.network import NetworkRateCalculator
from nova98.metrics.temperature import TemperatureProvider, get_platform_provider


class MetricsService:
    def __init__(
        self,
        temperature_provider: TemperatureProvider | None = None,
        gpu_provider: GPUProvider | None = None,
    ):
        self._temperature = temperature_provider or get_platform_provider()
        self._gpu = gpu_provider or get_platform_gpu_provider()
        self._network = NetworkRateCalculator()
        cpu_sample()  # prime psutil counter; first call is meaningless

    def read(self) -> SystemMetrics:
        download, upload = self._network.update()
        gpu = self._gpu.read()
        return SystemMetrics(
            cpu_percent=cpu_sample(),
            memory_percent=memory_sample(),
            cpu_temperature=self._temperature.get_cpu_temperature(),
            gpu_percent=gpu.usage,
            gpu_temperature=gpu.temperature,
            download_bytes_per_sec=download,
            upload_bytes_per_sec=upload,
            timestamp=datetime.now(),
        )
