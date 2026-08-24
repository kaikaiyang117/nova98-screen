"""Enumerate all HID interfaces and locate the AULA NOVA98 keyboard.

Read-only: this script never writes to the device.

Usage:
    python scripts/enumerate_hid.py [--all] [--output device_dump.json]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import hid

NOVA98_KEYWORDS = ("nova98", "nova 98", "aula")

FIELD_ORDER = (
    "vendor_id",
    "product_id",
    "release_number",
    "interface_number",
    "usage_page",
    "usage",
    "product_string",
    "manufacturer_string",
    "serial_number",
    "path",
)


def format_hex(value: int) -> str:
    return f"0x{value:04X}"


def describe_device(info: dict) -> str:
    lines = [
        "Device",
        "-" * 40,
        f"VID:PID       {format_hex(info['vendor_id'])}:{format_hex(info['product_id'])}",
        f"Manufacturer  {info.get('manufacturer_string') or '<unknown>'}",
        f"Product       {info.get('product_string') or '<unknown>'}",
        f"Serial        {info.get('serial_number') or '<none>'}",
        f"Interface     {info.get('interface_number')}",
        f"Usage Page    {format_hex(info.get('usage_page') or 0)}",
        f"Usage         {format_hex(info.get('usage') or 0)}",
        f"Path          {info.get('path')!r}",
    ]
    return "\n".join(lines)


def looks_like_nova98(info: dict) -> bool:
    haystack = " ".join(
        str(info.get(key) or "").lower()
        for key in ("product_string", "manufacturer_string")
    )
    return any(keyword in haystack for keyword in NOVA98_KEYWORDS)


def sanitize(info: dict) -> dict:
    cleaned = {}
    for key in FIELD_ORDER:
        value = info.get(key)
        if isinstance(value, bytes):
            value = value.decode("utf-8", errors="replace")
        cleaned[key] = value
    return cleaned


def main() -> int:
    parser = argparse.ArgumentParser(description="Enumerate HID devices (read-only).")
    parser.add_argument(
        "--all",
        action="store_true",
        help="print every HID device, not only likely NOVA98 candidates",
    )
    parser.add_argument(
        "--output",
        default="device_dump.json",
        help="path of the JSON dump (default: device_dump.json)",
    )
    args = parser.parse_args()

    devices = [sanitize(info) for info in hid.enumerate()]
    if not devices:
        print("No HID devices found.")
        return 1

    candidates = [d for d in devices if looks_like_nova98(d)]
    shown = devices if args.all else (candidates or devices)

    print(f"Found {len(devices)} HID interface(s), {len(candidates)} NOVA98 candidate(s).\n")
    for info in shown:
        print(describe_device(info))
        print()

    dump = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "nova98_candidates": candidates,
        "all_devices": devices,
    }
    Path(args.output).write_text(json.dumps(dump, indent=2, ensure_ascii=False))
    print(f"Results saved to {args.output}")

    if not candidates:
        print("\nWARNING: no candidate matched 'AULA/NOVA98'. Re-run with --all and inspect manually.")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
