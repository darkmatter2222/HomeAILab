import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import queue
import secrets
import threading
import time
import urllib.parse

from .common import alive, atomic_json, home, identity, read_json
from .device import DeviceLoop
from .focus import activate
from .model import Registry

LOG = logging.getLogger(__name__)


class InstanceLock:
    def __init__(self, root):
        self.path = root / "broker.lock"

    def __enter__(self):
        self.f = open(self.path, "a+b")
        try:
            self.f.seek(0)
            if os.name == "nt":
                import msvcrt
                if not self.f.read(1): self.f.write(b"0"); self.f.flush()
                self.f.seek(0)
                msvcrt.locking(self.f.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except Exception:
            self.f.close()
            raise
        return self

    def __exit__(self, *args):
        self.f.close()


class Broker:
    def __init__(self, root=None, mock=False, probe=alive, focus=activate):
        self.root = Path(root or home())
        self.root.mkdir(parents=True, exist_ok=True)
        self.config = {"fps": 10, "brightness": 45, "animations": True, "ready": True,
                       **(read_json(self.root / "config.json", {}) or {})}
        if not (self.root / "token").exists():
            fd = os.open(self.root / "token", os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(fd, "w", encoding="ascii") as f: f.write(secrets.token_hex(32))
        self.token = (self.root / "token").read_text(encoding="ascii").strip()
        self.registry = Registry(probe)
        self.stop = threading.Event()
        self.presses = queue.Queue(maxsize=64)
        self.device = DeviceLoop(self.registry, self.presses, self.stop, self.config, mock)
        self.focus = focus
        self.last_focus = None
        self.last_press = {}
        self.server = None

    def dispatch(self, method, path, body):
        if method == "GET" and path == "/v1/status":
            with self.registry.lock:
                overflow = sum(r["slot"] is None for r in self.registry.records.values())
            return {"epoch": self.registry.epoch, "device": dict(self.device.status),
                    "slots": self.registry.view(), "overflow": overflow,
                    "lastFocus": self.last_focus, "brokerPid": os.getpid()}
        if method == "POST" and path == "/v1/register":
            record = self.registry.upsert(body)
            return {"epoch": self.registry.epoch, "slot": record["slot"]}
        if path.startswith("/v1/instances/"):
            key = urllib.parse.unquote(path[len("/v1/instances/"):])
            if method == "PUT":
                return {"accepted": self.registry.snapshot(key, body), "epoch": self.registry.epoch}
            if method == "DELETE":
                self.registry.remove(key)
                return {"ok": True}
        if method == "POST" and path == "/v1/focus":
            return self.handle_press(body, synthetic=True)
        if method == "POST" and path == "/v1/stop":
            self.stop.set()
            return {"ok": True}
        raise KeyError("Unknown route")

    def handle_press(self, view, synthetic=False):
        r = self.registry.resolve(view.get("slot"), view.get("generation"), view.get("id"))
        if not r:
            return {"ok": False, "reason": "Empty or stale slot"}
        now = time.monotonic()
        if now - self.last_press.get(r["id"], -100) < .2:
            return {"ok": False, "reason": "Debounced"}
        self.last_press[r["id"]] = now
        outcome = self.focus(r)
        self.last_focus = {**outcome, "id": r["id"], "synthetic": synthetic, "time": time.time()}
        LOG.info("Focus %s", self.last_focus)
        return self.last_focus

    def serve(self):
        broker = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.0"
            def setup(self):
                super().setup()
                self.connection.settimeout(3)

            def log_message(self, *args): pass

            def handle_request(self):
                try:
                    if self.headers.get("Origin"):
                        self.send_json(403, {"error": "Browser origins are not accepted"}); return
                    expected = "Bearer " + broker.token
                    if not hmac.compare_digest(self.headers.get("Authorization", ""), expected):
                        self.send_json(401, {"error": "Unauthorized"}); return
                    size = int(self.headers.get("Content-Length", "0"))
                    if not 0 <= size <= 65536:
                        self.send_json(413, {"error": "Body too large"}); return
                    raw = self.rfile.read(size)
                    if len(raw) != size: raise ValueError("Incomplete body")
                    data = json.loads(raw) if raw else {}
                    if not isinstance(data, dict): raise ValueError("Expected object")
                    result = broker.dispatch(self.command, urllib.parse.urlsplit(self.path).path, data)
                    self.send_json(200, result)
                except KeyError:
                    self.send_json(404, {"error": "Not found; register again"})
                except (ValueError, TypeError) as e:
                    self.send_json(400, {"error": str(e)})
                except Exception:
                    LOG.exception("Request failed")
                    self.send_json(500, {"error": "Internal error; inspect broker.log"})

            def send_json(self, code, value):
                data = json.dumps(value).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                try: self.wfile.write(data)
                except OSError: pass

            do_GET = do_POST = do_PUT = do_DELETE = handle_request

        class Server(ThreadingHTTPServer):
            daemon_threads = True
            def __init__(self, *args):
                self.limit = threading.BoundedSemaphore(16)
                super().__init__(*args)
            def process_request(self, sock, address):
                if not self.limit.acquire(blocking=False):
                    sock.close(); return
                try: super().process_request(sock, address)
                except Exception:
                    self.limit.release(); raise
            def process_request_thread(self, *args):
                try: super().process_request_thread(*args)
                finally: self.limit.release()

        self.server = Server(("127.0.0.1", 0), Handler)
        atomic_json(self.root / "discovery.json", {"port": self.server.server_address[1],
                    "epoch": self.registry.epoch, "process": identity()})
        threads = [threading.Thread(target=self.server.serve_forever, daemon=True),
                   threading.Thread(target=self.device.run, daemon=True)]
        for thread in threads: thread.start()
        LOG.info("Broker ready on OS-assigned port %s", self.server.server_address[1])
        try:
            next_sweep = 0
            while not self.stop.is_set():
                if time.monotonic() >= next_sweep:
                    self.registry.sweep()
                    next_sweep = time.monotonic() + .5
                try: self.handle_press(self.presses.get(timeout=.1))
                except queue.Empty: pass
                except Exception: LOG.exception("Focus processing failed")
        finally:
            self.stop.set()
            self.server.shutdown()
            self.server.server_close()
            for thread in threads: thread.join(timeout=3)
            discovery = read_json(self.root / "discovery.json", {})
            if discovery.get("epoch") == self.registry.epoch:
                (self.root / "discovery.json").unlink(missing_ok=True)


def run(root=None, mock=False):
    root = Path(root or home())
    root.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(root / "broker.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    logging.basicConfig(level=logging.INFO, handlers=[handler],
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    try:
        with InstanceLock(root):
            broker = Broker(root, mock=mock)
            import signal
            for sig in (signal.SIGINT, signal.SIGTERM):
                signal.signal(sig, lambda *_: broker.stop.set())
            broker.serve()
    except (BlockingIOError, PermissionError):
        LOG.info("Broker already running or lock unavailable")
