"""Device adapter interface.

One device owner at a time. In option A the broker owns the Mini over HID; in
option B an Elgato plugin owns it and talks to this same broker. The broker only
ever talks to one adapter, so it never fights Elgato for the same device.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable, Optional

# A key press callback receives the 0-based slot index (row-major).
KeyPress = Callable[[int], None]


class DeviceAdapter(ABC):
    """A transport to the physical Mini: upload key images, read key presses."""

    name: str = "base"
    # Rows x cols of the Mini (2x3 = 6 keys), row-major.
    rows: int = 2
    cols: int = 3

    @abstractmethod
    def connect(self) -> bool:
        """Open the device. Return True on success."""

    @abstractmethod
    def close(self) -> None:
        """Release the device."""

    @abstractmethod
    def set_key_image(self, slot: int, image: bytes) -> bool:
        """Upload the full rendered image for a key slot.

        The image already bakes in color + identity + label so a stale title can
        never survive an otherwise-black key (research section 9).
        """

    def key_count(self) -> int:
        return self.rows * self.cols

    def poll(self) -> None:
        """Drain pending key edges. Push-based adapters (a library callback)
        leave this as a no-op; raw-HID adapters read buffered reports here and
        invoke the press handler. The broker loop calls this once per tick."""

    def set_key_press_handler(self, cb: KeyPress) -> None:
        """Register the callback invoked on a physical press edge (one edge per
        press; the adapter must not fire both down and up)."""
        self._on_key = cb

    def on_key(self, slot: int) -> None:
        handler = getattr(self, "_on_key", None)
        if handler is not None:
            handler(slot)

    def is_connected(self) -> bool:
        return getattr(self, "_connected", False)
