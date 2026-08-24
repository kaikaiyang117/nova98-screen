"""Upload a single solid-black test frame to the keyboard screen.

DANGEROUS: writes to the device's SPI flash path. Explicit user invocation only.

Usage:
    python scripts/test_single_frame.py [--text] [--yes]
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image, ImageDraw

from nova98.device.hid_device import Nova98Hid, HidError
from nova98.device.profiles import NOVA98
from nova98.display.uploader import SafetyError, UploadError, upload_single_frame

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def make_test_image(text: bool) -> Image.Image:
    image = Image.new("RGB", (NOVA98.width, NOVA98.height), (0, 0, 0))
    if text:
        draw = ImageDraw.Draw(image)
        from PIL import ImageFont

        try:
            font = ImageFont.truetype("Menlo.ttc", 22)
        except OSError:
            font = ImageFont.load_default()
        msg = "NOVA98 TEST"
        w = draw.textlength(msg, font=font)
        draw.text(((NOVA98.width - w) / 2, (NOVA98.height - 22) / 2), msg, font=font, fill=(255, 255, 255))
    return image


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--text", action="store_true", help="black background + 'NOVA98 TEST' text")
    parser.add_argument("--yes", action="store_true", help="skip interactive confirmation")
    args = parser.parse_args()

    image = make_test_image(args.text)
    print(f"Uploading ONE {NOVA98.width}x{NOVA98.height} black frame to slot 0.")
    print("Do NOT unplug the keyboard during upload.")

    if not args.yes:
        answer = input("Proceed? [y/N] ")
        if answer.strip().lower() != "y":
            print("Aborted.")
            return 1

    try:
        with Nova98Hid(NOVA98) as dev:
            result = upload_single_frame(image, dev)
    except (SafetyError, UploadError, HidError) as exc:
        print(f"FAILED: {exc}")
        print("STOPPED - do not retry blindly; check docs/reverse-engineering.md")
        return 2

    print(f"Done: {result.pages} pages, {result.acks} ACKs, {result.duration_s:.1f}s")
    print("Check the keyboard screen now: it should show a black image"
          + (" with 'NOVA98 TEST'." if args.text else "."))
    return 0


if __name__ == "__main__":
    sys.exit(main())
