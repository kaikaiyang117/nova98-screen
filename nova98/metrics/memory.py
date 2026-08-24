import psutil


def sample() -> float:
    return psutil.virtual_memory().percent
