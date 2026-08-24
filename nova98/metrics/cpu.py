import psutil


def sample(interval: int | None = None) -> float:
    """CPU usage percent. First call primes the counter; call again >=1s later."""
    return psutil.cpu_percent(interval=interval)
