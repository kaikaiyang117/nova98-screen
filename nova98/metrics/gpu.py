"""GPU provider. Failures never crash the metrics pipeline."""

from __future__ import annotations

import abc
import shutil
import subprocess
import sys
from dataclasses import dataclass


@dataclass
class GPUMetrics:
    usage: float | None = None
    temperature: float | None = None


class GPUProvider(abc.ABC):
    def read(self) -> GPUMetrics:
        try:
            return self._read()
        except Exception:  # noqa: BLE001 - provider must never crash the pipeline
            return GPUMetrics()

    @abc.abstractmethod
    def _read(self) -> GPUMetrics: ...


class NullGPUProvider(GPUProvider):
    def _read(self) -> GPUMetrics:
        return GPUMetrics()


class MacOSGPUProvider(GPUProvider):
    """Apple Silicon: powermetrics is the only real source but needs root.

    Without an elevated shell we return None and the UI/telemetry hides it.
    """

    def _read(self) -> GPUMetrics:
        if not shutil.which("powermetrics"):
            return GPUMetrics()
        try:
            out = subprocess.run(
                ["powermetrics", "--samplers", "gpu_power", "-i", "1", "-n", "1"],
                capture_output=True,
                text=True,
                timeout=6,
            ).stdout
        except (subprocess.TimeoutExpired, OSError):
            return GPUMetrics()

        usage = None
        for line in out.splitlines():
            if "GPU HW active residency" in line or "GPU active residency" in line:
                for token in line.replace("%", "").split():
                    try:
                        usage = float(token)
                        break
                    except ValueError:
                        continue
                if usage is not None:
                    break
        return GPUMetrics(usage=usage, temperature=None)


class NVMLGPUProvider(GPUProvider):
    """NVIDIA on Linux/Windows via pynvml if installed."""

    def _read(self) -> GPUMetrics:
        import pynvml  # optional dependency

        try:
            pynvml.nvmlInit()
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            usage = pynvml.nvmlDeviceGetUtilizationRates(handle).gpu
            temp = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
            return GPUMetrics(usage=float(usage), temperature=float(temp))
        finally:
            pynvml.nvmlShutdown()


def get_platform_gpu_provider() -> GPUProvider:
    if sys.platform == "darwin":
        return MacOSGPUProvider()
    if shutil.which("nvidia-smi"):
        try:
            import pynvml  # noqa: F401

            return NVMLGPUProvider()
        except ImportError:
            pass
    return NullGPUProvider()
