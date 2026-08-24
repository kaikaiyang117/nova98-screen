"""HID transport for NOVA98.

Interface roles (verified, docs/protocol.md):
- profile.control  = Interface 2 / usage page 0xFF68: control commands
- profile.display  = Interface 3 / usage page 0xFF67: TFT image stream

Safety: constructing this class sends nothing. All writes happen in explicit methods.
"""

from __future__ import annotations

import time

import hid

from nova98.device.profiles import DeviceProfile

ACK_TIMEOUT_MS = 2000
MAX_RETRIES = 3


class HidError(IOError):
    pass


class Nova98Hid:
    def __init__(self, profile: DeviceProfile):
        self.profile = profile
        self._control = None
        self._tft = None

    # -- lifecycle ---------------------------------------------------------

    def open(self) -> None:
        infos = hid.enumerate(vendor_id=self.profile.vendor_id, product_id=self.profile.product_id)

        if self._control is None:
            ctrl = self._match(infos, self.profile.control)
            if not ctrl:
                raise HidError(
                    f"control HID interface ({self.profile.control.interface_number} / "
                    f"{self.profile.control.usage_page:#06x}) not found"
                )
            self._control = hid.device()
            self._control.open_path(ctrl[0]["path"])

        if self._tft is None:
            tft = self._match(infos, self.profile.display)
            if not tft:
                raise HidError(
                    f"TFT HID interface ({self.profile.display.interface_number} / "
                    f"{self.profile.display.usage_page:#06x}) not found"
                )
            self._tft = hid.device()
            self._tft.open_path(tft[0]["path"])

    def _match(self, infos: list[dict], iface) -> list[dict]:
        return [
            i
            for i in infos
            if i["interface_number"] == iface.interface_number
            and (i.get("usage_page") or 0) == iface.usage_page
        ]

    def close(self) -> None:
        for dev in (self._control, self._tft):
            if dev is not None:
                try:
                    dev.close()
                except OSError:
                    pass
        self._control = None
        self._tft = None

    def __enter__(self) -> "Nova98Hid":
        self.open()
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    @property
    def opened_interfaces(self) -> tuple[str, str]:
        """For tests/diagnostics: which interfaces were opened."""
        roles = []
        if self._control is not None:
            roles.append(f"control=if{self.profile.control.interface_number}")
        if self._tft is not None:
            roles.append(f"tft=if{self.profile.display.interface_number}")
        return tuple(roles)  # type: ignore[return-value]

    # -- TFT stream channel --------------------------------------------------

    def write_tft_chunk(self, report: bytes, retries: int = MAX_RETRIES) -> bytes | None:
        """Send one 4104-byte TFT chunk and wait for the 55 41 ACK.

        `report` must be exactly 8 header + 4096 payload bytes.
        """
        if self._tft is None:
            raise HidError("TFT interface not open")
        if len(report) != 4104:
            raise HidError(f"TFT chunk is {len(report)} bytes, expected 4104")

        last_error: str | None = None
        for attempt in range(retries + 1):
            written = self._tft.write(b"\x00" + report)
            if written < 0:
                raise HidError("TFT chunk write failed")
            ack = self._tft.read(64, timeout_ms=ACK_TIMEOUT_MS)
            if ack:
                return bytes(ack)
            last_error = f"timeout on attempt {attempt + 1}"
        raise HidError(f"TFT ACK missing after {retries + 1} attempts ({last_error})")

    # -- control channel (0xAA-framed commands on FF68) ----------------------

    def send_control_command(self, cmd: int, data: bytes = b"", timeout_ms: int = 500,
                             max_retries: int = 0, response_cmd: int | None = None,
                             content_size: int | None = None) -> list[bytes]:
        """Generic An() framing: AA <cmd> <len> <addr LE16> ... data. Returns payloads."""
        if self._control is None:
            raise HidError("control interface not open")
        expected = response_cmd if response_cmd is not None else cmd
        size = content_size if content_size is not None else len(data)

        chunks = [data[i : i + 24] for i in range(0, len(data), 24)] or [b""]
        addr = 0
        payloads: list[bytes] = []
        for n, chunk in enumerate(chunks):
            pkt = bytearray(32)
            pkt[0] = 0xAA
            pkt[1] = cmd & 0xFF
            pkt[2] = len(chunk) & 0xFF
            pkt[3] = addr & 0xFF
            pkt[4] = (addr >> 8) & 0xFF
            pkt[6] = 1 if n == len(chunks) - 1 else 0
            pkt[8 : 8 + len(chunk)] = chunk

            for attempt in range(max_retries + 1):
                written = self._control.write(b"\x00" + bytes(pkt))
                if written < 0:
                    raise HidError(f"control write failed for cmd {cmd:#x}")
                resp = self._read_control_response(expected, timeout_ms)
                if resp is not None:
                    payloads.append(resp[8:])
                    break
            else:
                raise HidError(f"no ACK for control cmd {cmd:#x}")
            addr += len(chunk)
        _ = size
        return payloads

    def send_temporary_data(self, payload: bytes, max_retries: int = 0) -> list[bytes]:
        """cmd 52 SET_TEMPORARY_COMMAND_DATA (system status / clock).

        AULA HUB sends this with default timeout and no retries for the
        screen-info variant; ACK expected as `55 34` (same-cmd response).
        """
        return self.send_control_command(cmd=0x34, data=payload, max_retries=max_retries)

    def _read_control_response(self, expected_cmd: int, timeout_ms: int) -> bytes | None:
        deadline = time.monotonic() + timeout_ms / 1000
        while time.monotonic() < deadline:
            remaining = max(1, int((deadline - time.monotonic()) * 1000))
            resp = self._control.read(64, timeout_ms=remaining)
            if resp and resp[0] == 0x55 and resp[1] == expected_cmd:
                return bytes(resp)
        return None
