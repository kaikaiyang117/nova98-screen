"""Display backend boundary.

The runtime must not be hard-wired to the flash-backed cmd 80 path. If a
volatile / RAM-only display channel is ever found on NOVA98, it can be added
as another backend without touching scheduler logic.

No speculative backends are implemented: only the verified flash path exists.
"""

from __future__ import annotations

from typing import Protocol

from PIL import Image

from nova98.device.hid_device import Nova98Hid
from nova98.display.uploader import UploadResult, upload_single_frame


class DisplayBackend(Protocol):
    def show(self, image: Image.Image) -> UploadResult: ...


class FlashFramebufferBackend:
    """Verified cmd 80 path. Each upload writes keyboard SPI flash."""

    def __init__(self, hid_device: Nova98Hid):
        self._hid = hid_device

    @property
    def device(self) -> Nova98Hid:
        return self._hid

    def show(self, image: Image.Image) -> UploadResult:
        return upload_single_frame(image, self._hid)
