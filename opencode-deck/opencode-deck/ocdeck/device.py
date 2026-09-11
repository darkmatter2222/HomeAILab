"""HID adapter using the pip hidapi wheel, avoiding a manual hidapi.dll install."""
import logging
import queue
import threading
import time
from .art import frame

LOG = logging.getLogger(__name__)
MINI_PIDS = {0x0063, 0x0090, 0x00B3, 0x00B8}


class WheelTransport:
    """StreamDeck transport duck type backed by cython-hidapi's bundled library."""
    def __init__(self, info):
        self.info, self.handle = info, None
        self.lock = threading.RLock()

    def open(self):
        import hid
        with self.lock:
            if self.handle is None:
                h = hid.device()
                h.open_path(self.info["path"])
                h.set_nonblocking(True)
                self.handle = h

    def close(self):
        with self.lock:
            if self.handle:
                self.handle.close()
                self.handle = None

    def is_open(self):
        return self.handle is not None

    def connected(self):
        import hid
        return any(x["path"] == self.info["path"] for x in hid.enumerate(0x0FD9, self.product_id()))

    def path(self): return self.info["path"]
    def vendor_id(self): return self.info["vendor_id"]
    def product_id(self): return self.info["product_id"]

    def _call(self, method, *args):
        from StreamDeck.Transport.Transport import TransportError
        try:
            with self.lock:
                if self.handle is None:
                    raise OSError("Device is closed")
                return getattr(self.handle, method)(*args)
        except (OSError, ValueError) as e:
            raise TransportError(str(e)) from e

    def write(self, payload):
        result = self._call("write", bytes(payload))
        if result != len(payload):
            from StreamDeck.Transport.Transport import TransportError
            raise TransportError(f"Short HID write: {result}/{len(payload)}")
        return result

    def write_feature(self, payload): return self._call("send_feature_report", bytes(payload))
    def read_feature(self, report_id, length): return bytes(self._call("get_feature_report", report_id, length))
    def read(self, length):
        value = self._call("read", length)
        return bytes(value) if value else None


def enumerate_minis():
    import hid
    return [d for d in hid.enumerate(0x0FD9, 0) if d["product_id"] in MINI_PIDS]


class DeviceLoop:
    def __init__(self, registry, presses, stop, config, mock=False):
        self.registry, self.presses, self.stop, self.config, self.mock = registry, presses, stop, config, mock
        self.status = {"online": False, "mock": mock, "error": "Not connected", "frames": 0}
        self.presented = [None] * 6
        self.presented_lock = threading.Lock()
        self.deck = None

    def press(self, key, state):
        if not state or not 0 <= key < 6:
            return
        with self.presented_lock:
            view = self.presented[key]
            if view:
                try:
                    self.presses.put_nowait(dict(view))
                except queue.Full:
                    LOG.warning("Press queue full; dropping press")

    def run(self):
        from PIL import Image
        while not self.stop.is_set():
            try:
                if not self.mock:
                    from StreamDeck.Devices.StreamDeckMini import StreamDeckMini
                    from StreamDeck.ImageHelpers import PILHelper
                    devices = enumerate_minis()
                    serial = self.config.get("serial")
                    if serial:
                        devices = [d for d in devices if d.get("serial_number") == serial]
                    if len(devices) != 1:
                        raise RuntimeError(f"Found {len(devices)} matching Minis; select serial in config.json if multiple")
                    self.deck = StreamDeckMini(WheelTransport(devices[0]))
                    self.deck.open()
                    self.deck.set_brightness(int(self.config.get("brightness", 45)))
                    blank = PILHelper.to_native_key_format(self.deck, Image.new("RGB", (80, 80), "black"))
                    for k in range(6): self.deck.set_key_image(k, blank)
                    self.deck.set_key_callback(lambda deck, key, state: self.press(key, state))
                    self.status.update(serial=devices[0].get("serial_number"), productId=devices[0]["product_id"])
                self.status.update(online=True, error="")
                last, native = {}, {}
                next_probe = time.monotonic() + 2
                fps = max(1, min(15, int(self.config.get("fps", 10))))
                while not self.stop.is_set():
                    start = time.monotonic()
                    if not self.mock and start >= next_probe:
                        if not self.deck.is_open() or not self.deck.connected(): raise OSError("Mini disconnected")
                        next_probe = start + 2
                    views = self.registry.view()
                    if not any(v["id"] for v in views) and self.config.get("ready", True):
                        views[0] = {**views[0], "state": "ready"}
                    phase = int(start * 12) % 24 if self.config.get("animations", True) else 6
                    for k, v in enumerate(views):
                        key = (v["state"], v["label"], k, phase if v["state"] != "off" else 0)
                        if last.get(k) == key:
                            continue
                        if not self.mock:
                            if key not in native:
                                if len(native) > 1024: native.clear()
                                native[key] = PILHelper.to_native_key_format(self.deck, frame(*key))
                            self.deck.set_key_image(k, native[key])
                        with self.presented_lock:
                            self.presented[k] = dict(v)
                        last[k] = key
                        self.status["frames"] += 1
                    self.stop.wait(max(0, 1/fps - (time.monotonic() - start)))
            except Exception as error:
                LOG.warning("Device connection: %s", error)
                self.status.update(online=False, error=str(error))
            finally:
                if self.deck:
                    try:
                        if self.stop.is_set():
                            from StreamDeck.ImageHelpers import PILHelper
                            blank = PILHelper.to_native_key_format(self.deck, Image.new("RGB", (80, 80), "black"))
                            for k in range(6): self.deck.set_key_image(k, blank)
                    except Exception: pass
                    try: self.deck.close()
                    except Exception: pass
                    self.deck = None
                with self.presented_lock:
                    self.presented = [None] * 6
            self.stop.wait(2)
