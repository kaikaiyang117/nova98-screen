"""nova98-screen command line interface.

Commands:
    devices         list detected NOVA98 HID interfaces
    metrics         print current system metrics once
    telemetry       print the native telemetry values that would be sent
    preview         render dashboard to preview.png
    show            upload one static dashboard frame
    telemetry-test  send one cmd 52 telemetry status (single shot)
    run             dual-channel background runtime (fast + slow path)
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

from nova98.config import Config
from nova98.device.hid_device import Nova98Hid
from nova98.device.profiles import NOVA98
from nova98.display.uploader import SafetyError, UploadError, upload_single_frame
from nova98.metrics.service import MetricsService
from nova98.scheduler.runtime import RECONNECT_INTERVAL_S, ScreenRuntime
from nova98.telemetry.model import TelemetryStatus
from nova98.telemetry.sender import TelemetrySender, TelemetryTransportError

logger = logging.getLogger("nova98")


def setup_logging(debug: bool) -> None:
    Path("logs").mkdir(exist_ok=True)
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.FileHandler("logs/nova98-screen.log"),
            logging.StreamHandler(),
        ],
    )


def cmd_devices(_args) -> int:
    from nova98.device.discovery import find_interfaces

    interfaces = find_interfaces(NOVA98)
    if not interfaces:
        print(f"NOVA98 ({NOVA98.vendor_id:#06x}:{NOVA98.product_id:#06x}) not found.")
        return 1
    print(f"{NOVA98.name}  VID:PID {NOVA98.vendor_id:#06x}:{NOVA98.product_id:#06x}")
    for i in interfaces:
        role = {
            NOVA98.control.interface_number: f"control (FF68)" if i.usage_page == NOVA98.control.usage_page else "",
            NOVA98.display.interface_number: "TFT stream (FF67)",
        }.get(i.interface_number, "")
        print(
            f"  Interface {i.interface_number}  UsagePage {i.usage_page:#06x}  "
            f"Usage {i.usage:#06x}  {role}"
        )
    return 0


def _sample_metrics(config: Config | None = None):
    service = MetricsService()
    service.read()  # prime counters
    time.sleep(1.1)
    return service.read()


def cmd_metrics(_args) -> int:
    m = _sample_metrics()

    def fmt(value, suffix):
        return "--" if value is None else f"{value:.0f}{suffix}"

    def rate(v):
        if v is None:
            return "--"
        return f"{v / 1024 / 1024:.1f}MB/s" if v >= 1024 * 1024 else f"{v / 1024:.0f}KB/s"

    print(f"CPU        {fmt(m.cpu_percent, '%')}")
    print(f"RAM        {fmt(m.memory_percent, '%')}")
    print(f"TEMP       {fmt(m.cpu_temperature, '°C')}")
    print(f"GPU        {fmt(m.gpu_percent, '%')}")
    print(f"GPU TEMP   {fmt(m.gpu_temperature, '°C')}")
    print(f"DOWNLOAD   {rate(m.download_bytes_per_sec)}")
    print(f"UPLOAD     {rate(m.upload_bytes_per_sec)}")
    return 0


def cmd_telemetry(_args) -> int:
    from nova98.telemetry.mapper import metrics_to_telemetry

    status = metrics_to_telemetry(_sample_metrics())
    print("Native telemetry channel (cmd 52) values:")
    print(f"CPU      {status.cpu_usage if status.cpu_usage is not None else '--'}")
    print(f"CPU TEMP {status.cpu_temperature if status.cpu_temperature is not None else '--'}")
    print(f"GPU      {status.gpu_usage if status.gpu_usage is not None else '--'}")
    print(f"GPU TEMP {status.gpu_temperature if status.gpu_temperature is not None else '--'}")
    return 0


def cmd_preview(args) -> int:
    image = render_current(Config.load(args.config))
    out = Path(args.output)
    image.save(out)
    print(f"Saved {out.resolve()} ({image.size[0]}x{image.size[1]})")
    return 0


def render_current(config: Config):
    from nova98.renderer.renderer import render
    from nova98.renderer.state import static_display_state

    return render(static_display_state(_sample_metrics(config)))


def cmd_show(args) -> int:
    image = render_current(Config.load(args.config))
    try:
        with Nova98Hid(NOVA98) as dev:
            result = upload_single_frame(image, dev)
    except (UploadError, SafetyError, OSError) as exc:
        print(f"FAILED: {exc}")
        return 2
    print(f"Uploaded ({result.pages} chunks, {result.acks} ACKs, {result.duration_s:.1f}s)")
    return 0


def cmd_run(args) -> int:
    config = Config.load(args.config)
    runtime = ScreenRuntime(config)
    service = MetricsService()
    logger.info(
        "Starting dual-channel runtime (telemetry %.1fs / static min %.0fs)",
        config.telemetry.interval,
        config.refresh.min_interval,
    )
    service.read()  # prime counters

    last_connect_attempt = 0.0
    last_sample = 0.0
    try:
        while True:
            now = time.monotonic()

            if runtime.state != "CONNECTED":
                if now - last_connect_attempt >= RECONNECT_INTERVAL_S:
                    last_connect_attempt = now
                    runtime.tick(service.read())
                time.sleep(0.5)
                continue

            if now - last_sample >= max(0.25, config.telemetry.interval * 0.9):
                last_sample = now
                runtime.tick(service.read())
            time.sleep(0.1)
    except KeyboardInterrupt:
        logger.info("Stopped by user")
        runtime.shutdown()
    return 0


def cmd_telemetry_test(args) -> int:
    status = TelemetryStatus(
        cpu_usage=args.cpu,
        cpu_temperature=args.cpu_temp,
        gpu_usage=args.gpu,
        gpu_temperature=args.gpu_temp,
        temperature_current=args.current_temp,
        temperature_high=args.high_temp,
        temperature_low=args.low_temp,
        weather_code=args.weather,
        humidity=args.humidity,
    )
    from nova98.telemetry.encoder import encode_system_status

    payload = encode_system_status(status)
    print(f"TelemetryStatus: {status}")
    print(f"Encoded payload ({len(payload)} bytes): {payload.hex(' ')}")

    if args.dry_run:
        print("dry-run: not sent to device.")
        return 0

    try:
        with Nova98Hid(NOVA98) as dev:
            TelemetrySender(dev).send(status)
    except (TelemetryTransportError, OSError, ValueError) as exc:
        print(f"FAILED: {exc}")
        return 2
    print("Sent once. Check the keyboard screen.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="nova98-screen", description=__doc__)
    parser.add_argument("--debug", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    p_devices = sub.add_parser("devices", help="list detected NOVA98 HID interfaces")
    p_devices.set_defaults(func=cmd_devices)

    p_metrics = sub.add_parser("metrics", help="print current system metrics")
    p_metrics.set_defaults(func=cmd_metrics)

    p_tel = sub.add_parser("telemetry", help="show native telemetry values")
    p_tel.set_defaults(func=cmd_telemetry)

    p_preview = sub.add_parser("preview", help="render dashboard to preview.png")
    p_preview.add_argument("--config", default="config.yaml")
    p_preview.add_argument("--output", default="preview.png")
    p_preview.set_defaults(func=cmd_preview)

    p_show = sub.add_parser("show", help="upload one static frame")
    p_show.add_argument("--config", default="config.yaml")
    p_show.set_defaults(func=cmd_show)

    p_run = sub.add_parser("run", help="dual-channel background runtime")
    p_run.add_argument("--config", default="config.yaml")
    p_run.set_defaults(func=cmd_run)

    p_ttest = sub.add_parser(
        "telemetry-test", help="send one cmd 52 telemetry status (single shot)"
    )
    for name in (
        "--cpu", "--cpu-temp", "--gpu", "--gpu-temp", "--current-temp",
        "--high-temp", "--low-temp", "--weather", "--humidity",
    ):
        p_ttest.add_argument(name, type=int, default=None)
    p_ttest.add_argument("--dry-run", action="store_true", help="encode and print only")
    p_ttest.set_defaults(func=cmd_telemetry_test)

    args = parser.parse_args(argv)
    setup_logging(args.debug)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
