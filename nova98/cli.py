"""nova98-screen command line interface.

Commands:
    devices   list detected NOVA98 HID interfaces
    metrics   print current system metrics once
    preview   render dashboard to preview.png
    show      upload the dashboard to the keyboard screen once
    run       background refresh loop
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
from nova98.scheduler.daemon import RECONNECT_INTERVAL_S, ScreenDaemon
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
    import hid

    from nova98.device.discovery import find_interfaces

    interfaces = find_interfaces(NOVA98)
    if not interfaces:
        print(f"NOVA98 ({NOVA98.vendor_id:#06x}:{NOVA98.product_id:#06x}) not found.")
        return 1
    print(f"{NOVA98.name}  VID:PID {NOVA98.vendor_id:#06x}:{NOVA98.product_id:#06x}")
    for i in interfaces:
        role = {2: "control (FF68)", 3: "TFT stream (FF67)"}.get(i.interface_number, "")
        print(
            f"  Interface {i.interface_number}  UsagePage {i.usage_page:#06x}  "
            f"Usage {i.usage:#06x}  {role}"
        )
    return 0


def cmd_metrics(_args) -> int:
    service = MetricsService()
    service.read()  # prime CPU counter and network baseline
    time.sleep(1.1)
    m = service.read()

    def fmt(value, suffix):
        return "--" if value is None else f"{value:.0f}{suffix}"

    rate = lambda v: "--" if v is None else (
        f"{v / 1024 / 1024:.1f}MB/s" if v >= 1024 * 1024 else f"{v / 1024:.0f}KB/s"
    )
    print(f"CPU        {fmt(m.cpu_percent, '%')}")
    print(f"RAM        {fmt(m.memory_percent, '%')}")
    print(f"TEMP       {fmt(m.cpu_temperature, '°C')}")
    print(f"DOWNLOAD   {rate(m.download_bytes_per_sec)}")
    print(f"UPLOAD     {rate(m.upload_bytes_per_sec)}")
    return 0


def _current_image(config: Config):
    service = MetricsService()
    from nova98.renderer.renderer import render

    service.read()
    time.sleep(1.1)
    return render(service.read())


def cmd_preview(args) -> int:
    image = _current_image(Config.load(args.config))
    out = Path(args.output)
    image.save(out)
    print(f"Saved {out.resolve()} ({image.size[0]}x{image.size[1]})")
    return 0


def cmd_show(args) -> int:
    image = _current_image(Config.load(args.config))
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
    daemon = ScreenDaemon(config)
    service = MetricsService()
    logger.info("Starting run loop (min refresh %ss)", config.refresh.min_interval)

    # Prime counters.
    service.read()

    last_connect_attempt = 0.0
    try:
        while True:
            if daemon.state != "CONNECTED":
                now = time.monotonic()
                if now - last_connect_attempt >= RECONNECT_INTERVAL_S:
                    last_connect_attempt = now
                    daemon.tick(service.read())
                time.sleep(0.5)
                continue

            m = service.read()  # ~1s cadence via psutil interval
            daemon.tick(m)
            time.sleep(1.0)
    except KeyboardInterrupt:
        logger.info("Stopped by user")
        daemon.disconnect()
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
    p_metrics.add_argument("--config", default="config.yaml")
    p_metrics.set_defaults(func=cmd_metrics)

    p_preview = sub.add_parser("preview", help="render dashboard to preview.png")
    p_preview.add_argument("--config", default="config.yaml")
    p_preview.add_argument("--output", default="preview.png")
    p_preview.set_defaults(func=cmd_preview)

    p_show = sub.add_parser("show", help="upload dashboard once")
    p_show.add_argument("--config", default="config.yaml")
    p_show.set_defaults(func=cmd_show)

    p_run = sub.add_parser("run", help="background refresh loop")
    p_run.add_argument("--config", default="config.yaml")
    p_run.set_defaults(func=cmd_run)

    p_tel = sub.add_parser(
        "telemetry-test", help="send one cmd 52 telemetry status (single shot)"
    )
    for name, default in (
        ("--cpu", None),
        ("--cpu-temp", None),
        ("--gpu", None),
        ("--gpu-temp", None),
        ("--current-temp", None),
        ("--high-temp", None),
        ("--low-temp", None),
        ("--weather", None),
        ("--humidity", None),
    ):
        p_tel.add_argument(name, type=int, default=default)
    p_tel.add_argument("--dry-run", action="store_true", help="encode and print only")
    p_tel.set_defaults(func=cmd_telemetry_test)

    args = parser.parse_args(argv)
    setup_logging(args.debug)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
