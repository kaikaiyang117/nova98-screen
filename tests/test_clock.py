import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nova98.device.clock import encode_clock_payload


def test_clock_payload_layout():
    payload = encode_clock_payload(datetime(2026, 8, 25, 14, 30, 45))  # Tuesday
    assert len(payload) == 10
    assert payload[0] == 0x5A
    assert payload[1] == 1
    assert payload[2] == 0x5A
    assert payload[3] == 26          # year % 100
    assert payload[4] == 8
    assert payload[5] == 25
    assert payload[6] == 14
    assert payload[7] == 30
    assert payload[8] == 45
    assert payload[9] == 2           # Tuesday -> JS getDay() == 2


def test_weekday_mapping_matches_js_getday():
    # JS getDay(): Sunday=0. Python weekday(): Sunday=6.
    sunday = datetime(2026, 8, 30)   # a Sunday
    assert (sunday.weekday() + 1) % 7 == 0
    payload = encode_clock_payload(sunday)
    assert payload[9] == 0


def test_defaults_to_now():
    before = datetime.now()
    payload = encode_clock_payload()
    after = datetime.now()
    assert payload[3] in (before.year % 100, after.year % 100)
