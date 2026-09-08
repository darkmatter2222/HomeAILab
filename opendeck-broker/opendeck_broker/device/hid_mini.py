"""Direct-HID adapter for the Elgato Stream Deck Mini (option A).

The broker owns the Mini over HID after the individual device is disabled in
the Elgato app (Elgato 7.1+ "Preferences > Devices > Enabled"). This is the
supported way to avoid two programs overwriting the same Mini.

Protocol caveat (research section 3): the Mini uses a *different* HID protocol
from the larger Stream Decks. We therefore identify the Mini explicitly and
defer the image/key-report layout to python-elgato-streamdeck rather than
hard-coding another model's report bytes. Physical validation of the exact
image format and key-report indexing is done by tools/probe_device.py.
"""

from __future__ import annotations

from typing import Optional

from .base import DeviceAdapter

ELGATO_VENDOR_ID = 0x1D4F

# Stream Deck Mini is product 0x0002 in Elgato's HID table. The larger models
# (0x0000 / 0x0001 / 0x0003 / ...) are deliberately NOT matched here so we never
# grab the wrong device. Confirm against your physical Mini in probe_device.py.
MINI_PRODUCT_IDS = (0x0002,)


class ElgatoMiniHID(DeviceAdapter):
    name = "elgato-mini-hid"

    def __init__(self, serial: Optional[str] = None) -> None:
        self.serial = serial
        self._connected = False
        self._deck = None
        self._hid = None  # raw hid device, used as a fallback / for reads

    # ------------------------------------------------------------------ #
    @classmethod
    def library_available(cls) -> bool:
        try:
            import elgato_streamdeck  # noqa: F401
            return True
        except Exception:
            return False

    @classmethod
    def hid_available(cls) -> bool:
        try:
            import hid  # noqa: F401
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------ #
    def connect(self) -> bool:
        if self.library_available():
            return self._connect_library()
        if self.hid_available():
            return self._connect_raw_hid()
        return False

    def _connect_library(self) -> bool:
        import elgato_streamdeck

        try:
            self._deck = elgato_streamdeck.StreamDeck(
                serial=self.serial,
                key_down_event=self._on_key_down,
                key_up_event=None,  # one press edge only (down); ignore up
                brightness=1.0,
                key_sound=False,
            )
            self._connected = True
            return True
        except Exception:
            self._deck = None
            self._connected = False
            return False

    def _connect_raw_hid(self) -> bool:
        import hid

        for vid, pid in ((ELGATO_VENDOR_ID, p) for p in MINI_PRODUCT_IDS):
            for dev in hid.enumerate(vid, pid):
                if self.serial and dev.get("serial_number") != self.serial:
                    continue
                try:
                    self._hid = hid.device()
                    self._hid.open_path(dev["path"])
                    self._connected = True
                    return True
                except Exception:
                    self._hid = None
        return False

    def _on_key_down(self, key: int) -> None:
        # library delivers the 0-based key index; forward as a press edge
        self.on_key(key)

    def close(self) -> None:
        try:
            if self._deck is not None:
                self._deck.close()
        finally:
            if self._hid is not None:
                try:
                    self._hid.close()
                except Exception:
                    pass
            self._deck = None
            self._hid = None
            self._connected = False

    def set_key_image(self, slot: int, image: bytes) -> bool:
        if self._deck is not None:
            try:
                # python-elgato-streamdeck accepts raw bytes for the key image.
                self._deck.set_key_image(slot, image)
                return True
            except Exception:
                return False
        # raw hid path: the Mini protocol writes key images as multi-packet
        # reports. This is validated by probe_device.py; without it we return
        # False so the broker does not claim a render that did not happen.
        if self._hid is not None:
            try:
                self._hid.write(image)
                return True
            except Exception:
                return False
        return False
