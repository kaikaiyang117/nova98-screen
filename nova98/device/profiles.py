"""Device profiles. Values must come from real enumeration, never guessed.

Interface roles verified against AULA HUB JS and live device (docs/protocol.md):
- Interface 2 / usage page 0xFF68 = control channel
- Interface 3 / usage page 0xFF67 = TFT stream channel
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HidInterfaceProfile:
    interface_number: int
    usage_page: int


@dataclass(frozen=True)
class DeviceProfile:
    name: str

    vendor_id: int
    product_id: int

    control: HidInterfaceProfile
    display: HidInterfaceProfile

    width: int
    height: int

    max_frames: int


# Reference profile from the reverse-engineered SONiX-era F108 Pro protocol.
F108_PRO = DeviceProfile(
    name="AULA F108 Pro",
    vendor_id=0x0C45,
    product_id=0x800A,
    control=HidInterfaceProfile(interface_number=3, usage_page=0xFF13),
    display=HidInterfaceProfile(interface_number=2, usage_page=0xFF68),
    width=240,
    height=135,
    max_frames=141,
)

# Real values captured on 2026-08-25 via scripts/enumerate_hid.py (macOS),
# roles confirmed against AULA HUB WebHID JS.
NOVA98 = DeviceProfile(
    name="AULA NOVA98",
    vendor_id=0x38A6,
    product_id=0x273B,
    control=HidInterfaceProfile(interface_number=2, usage_page=0xFF68),
    display=HidInterfaceProfile(interface_number=3, usage_page=0xFF67),
    width=240,
    height=135,
    max_frames=141,
)

PROFILES = (F108_PRO, NOVA98)
