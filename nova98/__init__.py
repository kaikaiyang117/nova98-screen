"""NOVA98 keyboard TFT system monitor.

Safety: importing this package or constructing device objects must never
send any USB data. All writes go through explicit upload/test commands.
"""

__version__ = "0.1.0"
