"""Encoder for cmd 52 (SET_TEMPORARY_COMMAND_DATA) system status payload.

Buffer layout (from AULA HUB JS, `mke` in vendor.pretty.js):

    length: exactly 24 bytes
    byte[6]  = 0x5A ('Z') marker
    byte[12] = CPU usage        (0..100)
    byte[13] = CPU temperature  (signed int8)
    byte[14] = GPU usage        (0..100)
    byte[15] = GPU temperature  (signed int8)
    byte[16] = current temperature
    byte[17] = high temperature
    byte[18] = low temperature
    byte[19] = weather code     (0..23 per official UI)
    byte[20] = humidity         (0..100)

None handling: encoded as 0. This matches the official JS which builds a
zero-filled Uint8Array(24) and only writes fields it has data for; the
official UI always sends all fields, so 0 is the observed neutral value.
"""

from __future__ import annotations

from nova98.telemetry.model import TelemetryStatus

PAYLOAD_LENGTH = 24
Z_MARKER_OFFSET = 6
Z_MARKER_VALUE = 0x5A


def encode_i8(value: int) -> int:
    """Encode a signed int8 into its wire byte."""
    if value < -128 or value > 127:
        raise ValueError(f"int8 out of range: {value}")
    return value & 0xFF


def encode_temperature(value: int) -> int:
    """Official JS validates temperatures as -127..127 before writing &0xFF."""
    if value < -127 or value > 127:
        raise ValueError(f"temperature out of range -127..127: {value}")
    return encode_i8(value)


def _usage(value: int) -> int:
    if not 0 <= value <= 100:
        raise ValueError(f"usage out of range 0..100: {value}")
    return int(value)


def encode_system_status(status: TelemetryStatus) -> bytes:
    buf = bytearray(PAYLOAD_LENGTH)
    buf[Z_MARKER_OFFSET] = Z_MARKER_VALUE

    if status.cpu_usage is not None:
        buf[12] = _usage(status.cpu_usage)
    if status.cpu_temperature is not None:
        buf[13] = encode_temperature(status.cpu_temperature)
    if status.gpu_usage is not None:
        buf[14] = _usage(status.gpu_usage)
    if status.gpu_temperature is not None:
        buf[15] = encode_temperature(status.gpu_temperature)
    if status.temperature_current is not None:
        buf[16] = encode_temperature(status.temperature_current)
    if status.temperature_high is not None:
        buf[17] = encode_temperature(status.temperature_high)
    if status.temperature_low is not None:
        buf[18] = encode_temperature(status.temperature_low)
    if status.weather_code is not None:
        code = status.weather_code
        if not 0 <= code <= 23:
            raise ValueError(f"weather code out of range 0..23: {code}")
        buf[19] = code
    if status.humidity is not None:
        humidity = status.humidity
        if not 0 <= humidity <= 100:
            raise ValueError(f"humidity out of range 0..100: {humidity}")
        buf[20] = humidity

    return bytes(buf)
