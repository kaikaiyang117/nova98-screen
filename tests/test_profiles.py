import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nova98.device.hid_device import Nova98Hid
from nova98.device.profiles import NOVA98


def test_profile_semantics_match_verified_protocol():
    # Interface 2 / FF68 = control; Interface 3 / FF67 = TFT stream.
    assert NOVA98.control.interface_number == 2
    assert NOVA98.control.usage_page == 0xFF68
    assert NOVA98.display.interface_number == 3
    assert NOVA98.display.usage_page == 0xFF67


class FakeHidModule:
    """Minimal hid module double that records which paths were opened."""

    def __init__(self, infos):
        self.infos = infos
        self.opened: list[int] = []

    def enumerate(self, vendor_id=None, product_id=None):
        return [i for i in self.infos if i["vendor_id"] == vendor_id and i["product_id"] == product_id]


def _device_info(interface_number: int) -> dict:
    return {
        "vendor_id": NOVA98.vendor_id,
        "product_id": NOVA98.product_id,
        "interface_number": interface_number,
        "usage_page": {2: 0xFF68, 3: 0xFF67}[interface_number],
        "path": f"if{interface_number}".encode(),
        "product_string": "AULA NOVA98",
        "manufacturer_string": "AULA",
    }


def test_open_selects_control_interface_2_and_tft_interface_3(monkeypatch):
    opened_paths: list[bytes] = []

    class FakeDevice:
        def open_path(self, path):
            opened_paths.append(path)

        def close(self):
            pass

    fake = FakeHidModule([_device_info(0), _device_info(1), _device_info(2), _device_info(3)])
    monkeypatch.setattr("nova98.device.hid_device.hid", fake)
    monkeypatch.setattr("nova98.device.hid_device.hid.device", lambda: FakeDevice())

    dev = Nova98Hid(NOVA98)
    dev.open()
    try:
        assert sorted(opened_paths) == [b"if2", b"if3"]
        roles = dict(part.split("=") for part in dev.opened_interfaces)
        assert roles == {"control": "if2", "tft": "if3"}
    finally:
        dev.close()


def test_open_fails_when_control_interface_missing(monkeypatch):
    fake = FakeHidModule([_device_info(3)])  # only TFT present
    monkeypatch.setattr("nova98.device.hid_device.hid", fake)

    from nova98.device.hid_device import HidError

    dev = Nova98Hid(NOVA98)
    try:
        dev.open()
        raise AssertionError("expected HidError")
    except HidError as exc:
        assert "control" in str(exc)
