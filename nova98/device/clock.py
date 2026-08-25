"""Clock sync sub-command of cmd 52 (SET_TEMPORARY_COMMAND_DATA).

The ONLY cmd 52 variant officially used on NOVA98 (AULA HUB tftScreenSet
page, manual "sync time" button -> pke in vendor.pretty.js:121685):

    10-byte data buffer:
    [0] = 0x5A ('Z')
    [1] = 1
    [2] = 0x5A ('Z')
    [3] = year % 100
    [4] = month        (1..12)
    [5] = day          (1..31)
    [6] = hours        (0..23)
    [7] = minutes      (0..59)
    [8] = seconds      (0..59)
    [9] = weekday      (0..6)

Sent via generic AA-framing with default timeout and retries.
"""

from __future__ import annotations

import datetime as _dt

CLOCK_BUFFER_LENGTH = 10
Z_MARKER = 0x5A


def encode_clock_payload(now: _dt.datetime | None = None) -> bytes:
    """Build the official clock-sync payload for cmd 52."""
    now = now or _dt.datetime.now()
    buf = bytearray(CLOCK_BUFFER_LENGTH)
    buf[0] = Z_MARKER
    buf[1] = 1
    buf[2] = Z_MARKER
    buf[3] = now.year % 100
    buf[4] = now.month
    buf[5] = now.day
    buf[6] = now.hour
    buf[7] = now.minute
    buf[8] = now.second
    buf[9] = (now.weekday() + 1) % 7  # JS getDay(): Sunday=0..Saturday=6
    return bytes(buf)
