import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nova98.telemetry.encoder import (
    PAYLOAD_LENGTH,
    encode_i8,
    encode_system_status,
    encode_temperature,
)
from nova98.telemetry.model import TelemetryStatus


def test_payload_is_24_bytes_and_zero_defaulted():
    payload = encode_system_status(TelemetryStatus())
    assert len(payload) == PAYLOAD_LENGTH == 24
    # None -> 0 everywhere except the marker.
    assert payload[6] == 0x5A
    assert all(b == 0 for i, b in enumerate(payload) if i != 6)


def test_marker_byte():
    assert encode_system_status(TelemetryStatus(cpu_usage=1))[6] == 0x5A


def test_full_example_from_protocol_doc():
    payload = encode_system_status(
        TelemetryStatus(
            cpu_usage=63,
            cpu_temperature=55,
            gpu_usage=42,
            gpu_temperature=61,
        )
    )
    assert payload[12] == 63
    assert payload[13] == 55
    assert payload[14] == 42
    assert payload[15] == 61
    assert payload[16] == 0  # unset fields stay zero


def test_cpu_usage_boundaries():
    for value in (0, 50, 100):
        payload = encode_system_status(TelemetryStatus(cpu_usage=value))
        assert payload[12] == value


def test_gpu_usage_boundaries():
    for value in (0, 100):
        payload = encode_system_status(TelemetryStatus(gpu_usage=value))
        assert payload[14] == value


def test_temperatures_encoded_as_signed_int8():
    payload = encode_system_status(
        TelemetryStatus(cpu_temperature=45, gpu_temperature=-5)
    )
    assert payload[13] == 45          # +45 -> 0x2D
    assert payload[15] == 0xFB        # -5 -> 0xFB


def test_weather_humidity_ranges():
    status = TelemetryStatus(weather_code=23, humidity=88)
    payload = encode_system_status(status)
    assert payload[19] == 23
    assert payload[20] == 88


def test_invalid_usage_raises():
    with pytest.raises(ValueError):
        encode_system_status(TelemetryStatus(cpu_usage=-1))
    with pytest.raises(ValueError):
        encode_system_status(TelemetryStatus(cpu_usage=101))
    with pytest.raises(ValueError):
        encode_system_status(TelemetryStatus(gpu_usage=255))


def test_temperature_official_range_is_minus127_to_127():
    # Official AULA HUB JS validates -127..127 for every temperature field.
    assert encode_temperature(-127) == 0x81
    assert encode_temperature(127) == 0x7F
    with pytest.raises(ValueError):
        encode_system_status(TelemetryStatus(cpu_temperature=-128))
    with pytest.raises(ValueError):
        encode_system_status(TelemetryStatus(cpu_temperature=-129))
    with pytest.raises(ValueError):
        encode_system_status(TelemetryStatus(gpu_temperature=128))


def test_encode_i8_boundaries():
    assert encode_i8(-128) == 0x80
    assert encode_i8(-1) == 0xFF
    assert encode_i8(0) == 0x00
    assert encode_i8(127) == 0x7F
    with pytest.raises(ValueError):
        encode_i8(128)
    with pytest.raises(ValueError):
        encode_i8(-129)


def test_humidity_out_of_range_raises():
    with pytest.raises(ValueError):
        encode_system_status(TelemetryStatus(humidity=101))


def test_weather_code_official_range():
    assert encode_system_status(TelemetryStatus(weather_code=0))[19] == 0
    assert encode_system_status(TelemetryStatus(weather_code=23))[19] == 23
    with pytest.raises(ValueError):
        encode_system_status(TelemetryStatus(weather_code=24))
