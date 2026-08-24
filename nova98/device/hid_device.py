"""HID transport for control (feature reports) and LCD (output reports) interfaces.

Safety: constructing this class sends nothing. All writes happen in explicit methods.
"""

from __future__ import annotations

import time

import hid

from nova98.device.profiles import DeviceProfile

CMD_DELAY_S = 0.035
ACK_TIMEOUT_MS = 300


class HidError(IOError):
    pass


class Nova98Hid:
    def __init__(self, profile: DeviceProfile):
        self.profile = profile
        self._control: hid.device | None = None
        self._lcd: hid.device | None = None

    # -- lifecycle ---------------------------------------------------------

    def open(self) -> None:
        import hid as _hid

        infos = _hid.enumerate(vendor_id=self.profile.vendor_id, product_id=self.profile.product_id)

        if self._control is None:
            ctrl = [
                i
                for i in infos
                if i["interface_number"] == 3
                and (i.get("usage_page") or 0) == self.profile.control_usage_page
            ]
            if not ctrl:
                raise HidError("control HID interface not found")
            self._control = hid.device()
            self._control.open_path(ctrl[0]["path"])

        if self._lcd is None:
            lcd = [
                i
                for i in infos
                if i["interface_number"] == 2
                and (i.get("usage_page") or 0) == self.profile.display_usage_page
            ]
            if not lcd:
                raise HidError("LCD HID interface not found")
            self._lcd = hid.device()
            self._lcd.open_path(lcd[0]["path"])

    def close(self) -> None:
        for dev in (self._control, self._lcd):
            if dev is not None:
                try:
                    dev.close()
                except OSError:
                    pass
        self._control = None
        self._lcd = None

    def __enter__(self) -> "Nova98Hid":
        self.open()
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # -- control channel ---------------------------------------------------

    def send_command(self, payload: bytes, expect_ack: bool = True) -> bytes | None:
        """Send a 64-byte feature-report command on interface 3 and read back."""
        if self._control is None:
            raise HidError("control interface not open")
        if len(payload) > 64:
            raise HidError(f"command too long: {len(payload)}")

        report = b"\x00" + payload.ljust(64, b"\x00")
        written = self._control.send_feature_report(report)
        if written < 0:
            raise HidError("SET_FEATURE failed")
        time.sleep(CMD_DELAY_S)

        if not expect_ack:
            return None
        response = bytes(self._control.get_feature_report(0x00, 64))
        if not response:
            raise HidError("empty GET_FEATURE response")
        return response

    # -- LCD channel -------------------------------------------------------

    def write_page(self, page: bytes) -> bytes | None:
        """Write one <=4096-byte pixel page via output report; try to read ACK."""
        if self._lcd is None:
            raise HidError("LCD interface not open")
        if len(page) > 4096:
            raise HidError(f"page too large: {len(page)}")

        report = b"\x00" + page
        written = self._lcd.write(report)
        if written < 0:
            raise HidError("LCD page write failed")

        ack = self._lcd.read(64, timeout_ms=ACK_TIMEOUT_MS)
        return bytes(ack) if ack else None
