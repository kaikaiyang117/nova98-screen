"""Minimal protocol probe: send BEGIN (`04 18`) on the control interface and
read back the ACK. This is the smallest possible verification that NOVA98's
control channel speaks an F108 Pro-style feature-report protocol.

EXPLICIT WRITE: run only if you accept the keyboard receiving this command.
No pixel data is sent. No flash is written by BEGIN alone.

Usage:
    python scripts/probe_device.py [--yes]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import hid

from nova98.device.profiles import NOVA98

REPORT_ID_PREFIX = b"\x00"  # hidapi: unnumbered reports need a leading 0x00
CMD_BEGIN = bytes.fromhex("0418")
CMD_DELAY_S = 0.035


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--yes", action="store_true", help="skip interactive confirmation")
    args = parser.parse_args()

    interfaces = [
        i
        for i in hid.enumerate(vendor_id=NOVA98.vendor_id, product_id=NOVA98.product_id)
        if i["interface_number"] == 3 and i.get("usage_page") == NOVA98.control_usage_page
    ]
    if not interfaces:
        print("Control interface (3 / FF67) not found. Is the keyboard in USB wired mode?")
        return 1

    path = interfaces[0]["path"]
    print(f"Opening control interface via {path!r}")

    if not args.yes:
        answer = input("Send BEGIN (04 18) feature report to the keyboard? [y/N] ")
        if answer.strip().lower() != "y":
            print("Aborted.")
            return 1

    try:
        dev = hid.device()
        dev.open_path(path)
    except OSError as exc:
        print(f"Failed to open device: {exc}")
        return 1

    try:
        dev.send_feature_report(REPORT_ID_PREFIX + CMD_BEGIN)
        print("Sent BEGIN.")
        import time

        time.sleep(CMD_DELAY_S)
        response = dev.get_feature_report(0x00, 64)
        print(f"ACK ({len(response)} bytes): {bytes(response).hex(' ')}")
        ack = bytes(response)
        if len(ack) >= 4 and ack[3] == 0x01:
            print("Result: ACK signature byte[3]=0x01 matches F108 Pro convention.")
            print("Compatible so far. Next step would be image header + single frame.")
            return 0
        print("Result: unexpected ACK. DO NOT proceed with uploads; capture more data.")
        return 2
    finally:
        dev.close()


if __name__ == "__main__":
    sys.exit(main())
