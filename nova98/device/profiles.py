"""Device profiles. Values must come from real enumeration, never guessed."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DeviceProfile:
    name: str

    vendor_id: int
    product_id: int

    control_usage_page: int | None
    display_usage_page: int | None

    width: int
    height: int

    max_frames: int


# Reference profile from the reverse-engineered F108 Pro protocol.
F108_PRO = DeviceProfile(
    name="AULA F108 Pro",
    vendor_id=0x0C45,
    product_id=0x800A,
    control_usage_page=0xFF13,
    display_usage_page=0xFF68,
    width=240,
    height=135,
    max_frames=141,
)

# Real values captured on 2026-08-25 via scripts/enumerate_hid.py (macOS).
NOVA98 = DeviceProfile(
    name="AULA NOVA98",
    vendor_id=0x38A6,
    product_id=0x273B,
    control_usage_page=0xFF67,
    display_usage_page=0xFF68,
    width=240,
    height=135,
    max_frames=141,
)

PROFILES = (F108_PRO, NOVA98)
