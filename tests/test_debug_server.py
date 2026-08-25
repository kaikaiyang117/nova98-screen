import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nova98.debug.server import state_from_params


def test_params_to_state():
    st = state_from_params(
        {"cpu": "42", "ram": "60", "temp": "55", "down": "512", "up": "128"}
    )
    assert st.cpu_percent == 42
    assert st.memory_percent == 60
    assert st.cpu_temperature == 55
    assert st.download_bytes_per_sec == 512 * 1024  # KB/s -> B/s
    assert st.upload_bytes_per_sec == 128 * 1024


def test_missing_temp_stays_none():
    st = state_from_params({"cpu": "10", "ram": "50", "down": "0", "up": "0"})
    assert st.cpu_temperature is None
