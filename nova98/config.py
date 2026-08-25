"""Configuration loading."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class RefreshConfig:
    # Conservative: every dynamic value rides flash-backed cmd 80 frames,
    # so 60s min / 30min re-evaluation keeps wear negligible.
    min_interval: float = 60.0
    force_interval: float = 1800.0


@dataclass
class MetricsConfig:
    cpu: bool = True
    memory: bool = True
    temperature: bool = True
    # No on-screen consumer for GPU while native telemetry is unavailable.
    gpu: bool = False
    network: bool = True
    # Independent of telemetry cadence: how often SystemMetrics is sampled.
    sample_interval: float = 1.0


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
        # Single source of truth for defaults: the dataclasses themselves.
        # load() must never restate a magic number.
        defaults = cls()
        config = cls()
        if path is not None:
            path = Path(path)
            if path.exists():
                raw = yaml.safe_load(path.read_text()) or {}
            else:
                raw = {}
        else:
            default_path = Path("config.yaml")
            raw = yaml.safe_load(default_path.read_text()) or {} if default_path.exists() else {}

        d = defaults
        display = raw.get("display") or {}
        static_display = raw.get("static_display") or display
        refresh = static_display.get("refresh") or {}
        config.refresh = RefreshConfig(
            min_interval=float(refresh.get("min_interval", d.refresh.min_interval)),
            force_interval=float(refresh.get("force_interval", d.refresh.force_interval)),
        )
        metrics_raw = raw.get("metrics") or {}
        config.metrics = MetricsConfig(
            cpu=bool(metrics_raw.get("cpu", d.metrics.cpu)),
            memory=bool(metrics_raw.get("memory", d.metrics.memory)),
            temperature=bool(metrics_raw.get("temperature", d.metrics.temperature)),
            gpu=bool(metrics_raw.get("gpu", d.metrics.gpu)),
            network=bool(metrics_raw.get("network", d.metrics.network)),
            sample_interval=float(
                metrics_raw.get("sample_interval", d.metrics.sample_interval)
            ),
        )
        thresholds = raw.get("thresholds") or {}
        config.thresholds = ThresholdsConfig(
            cpu=float(thresholds.get("cpu", d.thresholds.cpu)),
            memory=float(thresholds.get("memory", d.thresholds.memory)),
            temperature=float(thresholds.get("temperature", d.thresholds.temperature)),
        )
        telemetry = raw.get("telemetry") or {}
        tel_thresholds = telemetry.get("thresholds") or {}
        config.telemetry = TelemetryConfig(
            enabled=bool(telemetry.get("enabled", d.telemetry.enabled)),
            interval=float(telemetry.get("interval", d.telemetry.interval)),
            force_interval=float(telemetry.get("force_interval", d.telemetry.force_interval)),
            thresholds={
                key: int(tel_thresholds.get(key, value))
                for key, value in d.telemetry.thresholds.items()
            },
        )
        layout = raw.get("layout") or {}
        config.layout = LayoutConfig(name=str(layout.get("name", d.layout.name)))
        config.validate()
        return config

    def validate(self) -> None:
        """Reject invalid configurations instead of failing mid-run."""
        m = self.metrics
        if m.sample_interval <= 0:
            raise ValueError(
                f"metrics.sample_interval must be > 0, got {m.sample_interval}"
            )
        r = self.refresh
        if r.min_interval <= 0:
            raise ValueError(f"refresh.min_interval must be > 0, got {r.min_interval}")
        if r.force_interval < r.min_interval:
            raise ValueError(
                f"refresh.force_interval ({r.force_interval}) must be >= "
                f"min_interval ({r.min_interval})"
            )
        t = self.telemetry
        if t.interval <= 0:
            raise ValueError(f"telemetry.interval must be > 0, got {t.interval}")
        if t.force_interval < t.interval:
            raise ValueError(
                f"telemetry.force_interval ({t.force_interval}) must be >= "
                f"interval ({t.interval})"
            )
        for name, value in (
            ("thresholds.cpu", self.thresholds.cpu),
            ("thresholds.memory", self.thresholds.memory),
            ("thresholds.temperature", self.thresholds.temperature),
        ):
            if value < 0:
                raise ValueError(f"{name} must be >= 0, got {value}")
        for name, delta in t.thresholds.items():
            if delta < 0:
                raise ValueError(f"telemetry.thresholds.{name} must be >= 0, got {delta}")
