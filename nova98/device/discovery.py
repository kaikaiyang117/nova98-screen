"""HID discovery helpers. Read-only: never sends USB data."""

from __future__ import annotations

from dataclasses import dataclass

import hid

from nova98.device.profiles import PROFILES, DeviceProfile


@dataclass(frozen=True)
class HidInterface:
    vendor_id: int
    product_id: int
    interface_number: int
    usage_page: int
    usage: int
    path: str
    product_string: str
    manufacturer_string: str


def find_interfaces(profile: DeviceProfile) -> list[HidInterface]:
    """Return all HID interfaces matching a profile's VID/PID."""
    result = []
    for info in hid.enumerate(vendor_id=profile.vendor_id, product_id=profile.product_id):
        result.append(
            HidInterface(
                vendor_id=info["vendor_id"],
                product_id=info["product_id"],
                interface_number=info["interface_number"],
                usage_page=info.get("usage_page") or 0,
                usage=info.get("usage") or 0,
                path=info["path"].decode() if isinstance(info["path"], bytes) else info["path"],
                product_string=info.get("product_string") or "",
                manufacturer_string=info.get("manufacturer_string") or "",
            )
        )
    return result


def detect_device() -> DeviceProfile | None:
    """Return the first known profile whose VID/PID is present on the bus."""
    for profile in PROFILES:
        if find_interfaces(profile):
            return profile
    return None
