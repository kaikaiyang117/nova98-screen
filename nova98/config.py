"""Configuration loading."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class RefreshConfig:
    min_interval: float = 30.0
    force_interval: float = 300.0


@dataclass
class MetricsConfig:
    cpu: bool = True
    memory: bool = True
    temperature: bool = True
    gpu: bool = True
    network: bool = True


@dataclass
class ThresholdsConfig:
    cpu: float = 10.0
    memory: float = 5.0
    temperature: float = 3.0


@dataclass
class TelemetryConfig:
    # Default OFF: NOVA98 firmware ACKs cmd 52 but renders nothing
    # (docs/native-telemetry.md). Keep for future firmware / other models.
    enabled: bool = False
    interval: float = 1.0
    force_interval: float = 5.0
    thresholds: dict = field(default_factory=lambda: {"cpu": 1, "gpu": 1, "temperature": 1})


@dataclass
class LayoutConfig:
    name: str = "system"


@dataclass
class Config:
    refresh: RefreshConfig = field(default_factory=RefreshConfig)
    metrics: MetricsConfig = field(default_factory=MetricsConfig)
    thresholds: ThresholdsConfig = field(default_factory=ThresholdsConfig)
    telemetry: TelemetryConfig = field(default_factory=TelemetryConfig)
    layout: LayoutConfig = field(default_factory=LayoutConfig)

    # Alias: static_display section maps onto refresh config.
    @property
    def static_display(self) -> RefreshConfig:
        return self.refresh

    @classmethod
    def load(cls, path: str | Path | None = None) -> "Config":
        config = cls()
        if path is None:
            path = Path("config.yaml")
            if not path.exists():
                return config
        path = Path(path)
        if not path.exists():
            return config
        raw = yaml.safe_load(path.read_text()) or {}
        display = raw.get("display") or {}
        static_display = raw.get("static_display") or display
        refresh = static_display.get("refresh") or {}
        config.refresh = RefreshConfig(
            min_interval=float(refresh.get("min_interval", 30)),
            force_interval=float(refresh.get("force_interval", 300)),
        )
        metrics_raw = raw.get("metrics") or {}
        config.metrics = MetricsConfig(
            cpu=bool(metrics_raw.get("cpu", True)),
            memory=bool(metrics_raw.get("memory", True)),
            temperature=bool(metrics_raw.get("temperature", True)),
            gpu=bool(metrics_raw.get("gpu", True)),
            network=bool(metrics_raw.get("network", True)),
        )
        thresholds = raw.get("thresholds") or {}
        config.thresholds = ThresholdsConfig(
            cpu=float(thresholds.get("cpu", 10)),
            memory=float(thresholds.get("memory", 5)),
            temperature=float(thresholds.get("temperature", 3)),
        )
        telemetry = raw.get("telemetry") or {}
        tel_thresholds = telemetry.get("thresholds") or {}
        config.telemetry = TelemetryConfig(
            enabled=bool(telemetry.get("enabled", False)),
            interval=float(telemetry.get("interval", 1)),
            force_interval=float(telemetry.get("force_interval", 5)),
            thresholds={
                "cpu": int(tel_thresholds.get("cpu", 1)),
                "gpu": int(tel_thresholds.get("gpu", 1)),
                "temperature": int(tel_thresholds.get("temperature", 1)),
            },
        )
        layout = raw.get("layout") or {}
        config.layout = LayoutConfig(name=str(layout.get("name", "system")))
        return config
