"""Loopback REST API for the broker.

Binds to loopback and requires the locally stored random token (header
`X-OpenDeck-Token`). Endpoints follow research section 7. The push channel for
the deck consumer is a Server-Sent Events stream at `/v1/deck` (a thin,
dependency-free stand-in for the WebSocket endpoint; the payload contract is
the same full-snapshot / incremental-update messages).
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional

from .broker import Broker
from .config import Config
from .model import Status
from .opencode.adapter import OpenCodeAdapter


class _Handler(BaseHTTPRequestHandler):
    broker: Broker = None  # type: ignore[assignment]
    adapter: OpenCodeAdapter = None  # type: ignore[assignment]
    token: str = ""
    _deck_subscribers: list = []
    _deck_lock = threading.Lock()

    def log_message(self, *args) -> None:  # silence
        pass

    def _send(self, code: int, obj: dict) -> None:
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self) -> bool:
        return self.headers.get("X-OpenDeck-Token") == self.token

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length", "0") or 0)
        raw = self.rfile.read(n) if n else b"{}"
        try:
            return json.loads(raw.decode() or "{}")
        except Exception:
            return {}

    def _notify_deck(self, msg: dict) -> None:
        with self._deck_lock:
            subs = list(self._deck_subscribers)
        for q in subs:
            try:
                q.put(msg)
            except Exception:
                pass

    # ------------------------------------------------------------------ #
    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/v1/display":
            if not self._authorized():
                return self._send(401, {"error": "unauthorized"})
            return self._send(200, {"frame": self._frame_payload()})
        if self.path == "/v1/diagnostics":
            if not self._authorized():
                return self._send(401, {"error": "unauthorized"})
            return self._send(200, self.broker.diagnostics())
        if self.path == "/v1/deck":
            return self._sse()
        return self._send(404, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        if not self._authorized():
            return self._send(401, {"error": "unauthorized"})
        if self.path == "/v1/instances/register":
            return self._register()
        if self.path.startswith("/v1/instances/") and self.path.endswith("/heartbeat"):
            iid = self.path.split("/")[3]
            epoch = self.adapter.heartbeat(iid)
            return self._send(200 if epoch else 404, {"broker_epoch": epoch})
        if self.path == "/v1/focus":
            b = self._body()
            res = self.broker.focus_instance(b.get("instanceId", ""), b.get("expectedGeneration"))
            return self._send(200, {"status": res.status.value, "hwnd": res.hwnd, "detail": res.detail})
        return self._send(404, {"error": "not_found"})

    def do_PUT(self) -> None:  # noqa: N802
        if not self._authorized():
            return self._send(401, {"error": "unauthorized"})
        if self.path.startswith("/v1/instances/") and self.path.endswith("/snapshot"):
            return self._snapshot()
        return self._send(404, {"error": "not_found"})

    def do_DELETE(self) -> None:  # noqa: N802
        if not self._authorized():
            return self._send(401, {"error": "unauthorized"})
        if self.path.startswith("/v1/instances/"):
            iid = self.path.split("/")[3]
            ok = self.adapter.detach(iid)
            self.broker.render()
            self._notify_deck({"type": "snapshot", "frame": self._frame_payload()})
            return self._send(200 if ok else 404, {"detached": ok})
        return self._send(404, {"error": "not_found"})

    # ------------------------------------------------------------------ #
    def _register(self) -> None:
        b = self._body()
        iid, slot = self.adapter.register_launch(
            directory=b.get("directory", ""),
            alias=b.get("alias", ""),
            pid=int(b.get("pid", 0)),
            start_time=b.get("startTime"),
            focus_target=b.get("focusTarget"),
        )
        self.broker.render()
        self._notify_deck({"type": "snapshot", "frame": self._frame_payload()})
        self._send(200, {"instanceId": iid, "slot": slot, "broker_epoch": self.adapter.producer_epoch})

    def _snapshot(self) -> None:
        b = self._body()
        iid = self.path.split("/")[3]
        launch = next((l for l in self.adapter.launches() if l.instance_id == iid), None)
        if launch is None:
            return self._send(404, {"error": "not_found"})
        status = Status(b.get("status", launch.instance.status.value))
        launch.instance.set_status(status)
        launch.instance.pending_permission_ids = list(b.get("pendingPermissionIds", []))
        launch.instance.pending_question_ids = list(b.get("pendingQuestionIds", []))
        seq = self.adapter._next_seq()  # noqa: SLF001
        launch.instance.sequence = seq
        applied = self.adapter.registry.accept_snapshot(launch.instance, self.adapter.producer_epoch, seq)
        self.broker.render()
        self._notify_deck({"type": "update", "frame": self._frame_payload()})
        self._send(200 if applied else 409, {"applied": applied})

    def _frame_payload(self) -> list:
        return [
            {
                "slot": s.slot,
                "instanceId": s.instance_id,
                "generation": s.generation,
                "appearance": s.appearance.value,
                "label": s.label,
            }
            for s in self.broker.registry.frame()
        ]

    def _sse(self) -> None:
        import queue

        q: "queue.Queue" = queue.Queue()
        with self._deck_lock:
            self._deck_subscribers.append(q)
        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(b"retry: 2000\n\n")
            self.wfile.write(self._event({"type": "snapshot", "frame": self._frame_payload()}))
            while True:
                msg = q.get()
                self.wfile.write(self._event(msg))
                self.wfile.flush()
        except Exception:
            pass
        finally:
            with self._deck_lock:
                if q in self._deck_subscribers:
                    self._deck_subscribers.remove(q)

    @staticmethod
    def _event(obj: dict) -> bytes:
        return f"data: {json.dumps(obj)}\n\n".encode()


class ApiServer:
    def __init__(self, broker: Broker, adapter: OpenCodeAdapter, config: Config) -> None:
        self.broker = broker
        self.adapter = adapter
        self.config = config
        self._httpd: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    def start(self, port: Optional[int] = None) -> int:
        port = port if port is not None else self.config.port
        _Handler.broker = self.broker
        _Handler.adapter = self.adapter
        _Handler.token = self.config.token()
        with _Handler._deck_lock:
            _Handler._deck_subscribers.clear()

        def notify() -> None:  # pragma: no cover - hook for external renders
            pass

        self._httpd = ThreadingHTTPServer((self.config.host, port), _Handler)
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()
        return self._httpd.server_address[1]

    def stop(self) -> None:
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None

    @property
    def token(self) -> str:
        return _Handler.token

    def port(self) -> int:
        return self._httpd.server_address[1] if self._httpd else 0
