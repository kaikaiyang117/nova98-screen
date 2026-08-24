"""Platform temperature providers. Never assume psutil sensors exist."""

from __future__ import annotations

import abc
import shutil
import subprocess
import sys

import psutil


class TemperatureProvider(abc.ABC):
    @abc.abstractmethod
    def get_cpu_temperature(self) -> float | None: ...


class LinuxTemperatureProvider(TemperatureProvider):
    def get_cpu_temperature(self) -> float | None:
        try:
            sensors = psutil.sensors_temperatures()  # type: ignore[attr-defined]
        except (AttributeError, OSError):
            sensors = {}
        for key in ("coretemp", "k10temp", "cpu_thermal", "acpitz", "x86_pkg_temp"):
            entries = sensors.get(key)
            if entries:
                return float(entries[0].current)
        for entries in sensors.values():
            if entries and entries[0].current and entries[0].current > 0:
                return float(entries[0].current)
        return None


class MacOSTemperatureProvider(TemperatureProvider):
    """macOS has no psutil temperature support; try local tools, else None."""

    def get_cpu_temperature(self) -> float | None:
        # osx-cpu-temp / aula-free SMC readers, if the user installed them.
        for tool, args in (("osx-cpu-temp", []), ("smctemp", ["-c"])):
            path = shutil.which(tool)
            if not path:
                continue
            try:
                out = subprocess.run(
                    [path, *args], capture_output=True, text=True, timeout=3
                ).stdout
                return self._parse(out)
            except (subprocess.TimeoutExpired, OSError):
                continue
        # powermetrics needs root; try anyway in case of elevated shell.
        if shutil.which("powermetrics"):
            try:
                out = subprocess.run(
                    ["powermetrics", "--samplers", "smc", "-i", "1", "-n", "1"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                ).stdout
                return self._parse_powermetrics(out)
            except (subprocess.TimeoutExpired, OSError):
                pass
        return None

    @staticmethod
    def _parse(output: str) -> float | None:
        for token in output.replace("\u00b0", " ").split():
            try:
                value = float(token)
            except ValueError:
                continue
            if 0 < value < 150:
                return value
        return None

    @staticmethod
    def _parse_powermetrics(output: str) -> float | None:
        for line in output.splitlines():
            if "CPU die temperature" in line or "die temperature" in line.lower():
                for token in line.replace("C", "").split():
                    try:
                        value = float(token)
                    except ValueError:
                        continue
                    if 0 < value < 150:
                        return value
        return None


class WindowsTemperatureProvider(TemperatureProvider):
    def get_cpu_temperature(self) -> float | None:
        try:
            sensors = psutil.sensors_temperatures()  # type: ignore[attr-defined]
        except (AttributeError, OSError):
            return None
        for entries in sensors.values():
            if entries and entries[0].current:
                return float(entries[0].current)
        return None


def get_platform_provider() -> TemperatureProvider:
    if sys.platform == "darwin":
        return MacOSTemperatureProvider()
    if sys.platform == "win32":
        return WindowsTemperatureProvider()
    return LinuxTemperatureProvider()
