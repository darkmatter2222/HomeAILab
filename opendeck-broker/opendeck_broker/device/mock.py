"""In-memory device adapter for headless unit tests and the self-test.

It records every uploaded image and lets a test inject physical key presses. It
is NOT physical evidence: a pass here proves the broker's render/press path, not
that the real Mini displayed the image or received the press (research section
14 keeps those distinct).
"""

from __future__ import annotations

from typing import Optional

from .base import DeviceAdapter


class MockDevice(DeviceAdapter):
    name = "mock"

    def __init__(self, rows: int = 2, cols: int = 3) -> None:
        self.rows = rows
        self.cols = cols
        self._connected = False
        self._on_key = None
        # slot -> last uploaded image bytes
        self.images: dict[int, bytes] = {}
        # every press edge the broker observed, in order: (slot,)
        self.presses: list[int] = []

    def connect(self) -> bool:
        self._connected = True
        return True

    def close(self) -> None:
        self._connected = False

    def set_key_image(self, slot: int, image: bytes) -> bool:
        if not self._connected:
            return False
        self.images[slot] = image
        return True

    def inject_press(self, slot: int) -> None:
        """Simulate one physical press edge on a slot."""
        self.presses.append(slot)
        self.on_key(slot)

    def uploaded_count(self) -> int:
        return len(self.images)

    def black_frame(self) -> None:
        """Convenience for tests: upload black to every key."""
        for i in range(self.key_count()):
            self.images[i] = b"\x00" * 4
