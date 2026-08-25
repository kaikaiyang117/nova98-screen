"""PreparedFrame: the single artifact produced per static refresh candidate.

Invariant guaranteed by construction:
the image used for hash computation, the image sent to the backend,
and the digest committed on success all refer to this one object.
"""

from __future__ import annotations

from dataclasses import dataclass

from PIL import Image

from nova98.renderer.state import StaticDisplayState


@dataclass(frozen=True)
class PreparedFrame:
    state: StaticDisplayState
    image: Image.Image
    digest: str
    reason: str
