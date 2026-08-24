import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nova98.metrics import network as network_module
from nova98.metrics.network import NetworkRateCalculator


class FakeCounters:
    def __init__(self, rx, tx):
        self.bytes_recv = rx
        self.bytes_sent = tx


class FakePsutil:
    def __init__(self, counters_seq):
        self._seq = list(counters_seq)

    def net_io_counters(self):
        if len(self._seq) > 1:
            return self._seq.pop(0)
        return self._seq[0]


class FakeTime:
    def __init__(self, now):
        self.now = now

    def monotonic(self):
        return self.now


def test_rate_calculation(monkeypatch):
    fake_psutil = FakePsutil([FakeCounters(1_000_000, 500_000), FakeCounters(2_000_000, 600_000)])
    monkeypatch.setattr(network_module.psutil, "net_io_counters", fake_psutil.net_io_counters)
    fake_time = FakeTime(100.0)
    monkeypatch.setattr(network_module.time, "monotonic", lambda: fake_time.now)

    calc = NetworkRateCalculator()
    fake_time.now = 110.0  # 10 seconds later
    down, up = calc.update()

    assert down == 100_000.0  # (2_000_000 - 1_000_000) / 10
    assert up == 10_000.0     # (600_000 - 500_000) / 10


def test_counter_reset_does_not_spike(monkeypatch):
    fake_psutil = FakePsutil([FakeCounters(1_000_000, 500_000), FakeCounters(100, 100)])
    monkeypatch.setattr(network_module.psutil, "net_io_counters", fake_psutil.net_io_counters)
    fake_time = FakeTime(100.0)
    monkeypatch.setattr(network_module.time, "monotonic", lambda: fake_time.now)

    calc = NetworkRateCalculator()
    fake_time.now = 105.0
    down, up = calc.update()

    # Reset detected: no bogus rate this cycle.
    assert down is None and up is None

    fake_time.now = 115.0
    down, up = calc.update()
    assert down == 0.0 and up == 0.0
