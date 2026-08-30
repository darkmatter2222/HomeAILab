#!/usr/bin/env python3
"""
qwen38-gpu-router
=================
Dynamic, priority-aware ingress router for two Qwen3.8-27B inference backends:

    priority 1 : RedPCv2 RTX 5090  (vLLM,   192.168.86.37:8006)  cap = MAX_SEQS (default 2)
    priority 2 : Databrick RTX 3090 (llama, host.docker.internal:8006) cap = 1

Routing policy (dynamic, re-probed every PROBE_INTERVAL seconds):
  - Discover each backend's *permissible active-request capacity* live:
        * vLLM  -> vllm:num_requests_running + vllm:num_requests_waiting  (from /metrics)
        * llama -> /slots  -> number of slots with is_processing==true
  - A backend is "available" when (configured_cap - backend_busy - router_inflight) >= 1
    AND it is healthy.
  - Route priority-1 first; if it is full, spill to priority-2; if BOTH are at
    their live capacity, return 503 (the ONLY error that means "at max capacity").
  - Sticky sessions: a session id (from header/body) is pinned to a healthy backend
    so a conversation stays on the GPU that holds its KV/prefix cache.

Auth: a single API key (ROUTER_API_KEY) accepted as `x-api-key`,
`Authorization: Bearer <key>`, or `Authorization: <key>` (Anthropic style).
This is what you point Claude Code at (base URL -> this router, key -> this key).

Surfaces a machine-readable snapshot at GET /router/status for the UI.
Also surfaces Prometheus text-format gauges at GET /router/metrics so the
GPU-fleet Grafana dashboard can scrape the router (qwen38_router_* metrics).

Env vars (all overridable):
  ROUTER_PORT            (8010)
  ROUTER_API_KEY         (optional; if set, requests must present it)
  RED5090_URL            (http://192.168.86.37:8006)
  RED5090_CAP            (2)          # vLLM --max-num-seqs
  RED5090_KIND           (vllm)
  RED3090_URL            (http://host.docker.internal:8006)
  RED3090_CAP            (1)          # llama --parallel
  RED3090_KIND           (llama)
  PROBE_INTERVAL         (2.0)       # seconds between live capacity probes
  SESSION_TTL_SECONDS    (1800)
  CONNECT_TIMEOUT_SECONDS(5)
  BACKEND_PROBE_TIMEOUT  (2.0)
  MAX_REQUEST_SECONDS    (43200)     # per-request hard ceiling (long generations)
  VISION_BACKEND         (dgxsparx)  # backend that image requests are force-routed
                                      # to (empty = disable image detection); never
                                      # spills an image to a text-only backend.
"""
import asyncio
import json
import logging
import os
import re
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx
from fastapi import FastAPI, Request
from fastapi import Response
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse

LOG = logging.getLogger("qwen38-gpu-router")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"),
                    format="%(asctime)s %(levelname)s %(message)s")

# ---------------------------------------------------------------- verbose logging
# A bounded in-memory ring of the last N log lines, exposed at GET /router/logs
# so the live tail can be read *from the router* (no SSH, no `docker logs`).
# The container's own json-file driver ALSO rolls on disk (max-size/max-file in
# the stack YAML) -- the ring is the "last N" view, the json-file the full history.
LOG_RING_MAX = int(os.getenv("LOG_RING_MAX", "2000"))


class _RingBuffer(logging.Handler):
    """Bounded queue of formatted log lines for the /router/logs endpoint."""
    def __init__(self, maxlen: int):
        super().__init__()
        from collections import deque
        self.q: "deque[str]" = deque(maxlen=maxlen)

    def emit(self, record: logging.LogRecord) -> None:
        self.q.append(self.format(record))


_RING: "_RingBuffer"
_RING = _RingBuffer(LOG_RING_MAX)
_RING.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
LOG.addHandler(_RING)


def tail_lines(n: int = 200) -> List[str]:
    n = max(1, min(int(n), LOG_RING_MAX))
    return list(_RING.q)[-n:]

# ---------------------------------------------------------------- config
ROUTER_HOST = os.getenv("ROUTER_HOST", "0.0.0.0")
ROUTER_PORT = int(os.getenv("ROUTER_PORT", "8010"))
ROUTER_API_KEY = os.getenv("ROUTER_API_KEY", "").strip()
SESSION_TTL_SECONDS = int(os.getenv("SESSION_TTL_SECONDS", "1800"))
CONNECT_TIMEOUT_SECONDS = float(os.getenv("CONNECT_TIMEOUT_SECONDS", "5"))
BACKEND_PROBE_TIMEOUT = float(os.getenv("BACKEND_PROBE_TIMEOUT", "2.0"))
MAX_REQUEST_SECONDS = float(os.getenv("MAX_REQUEST_SECONDS", "43200"))
PROBE_INTERVAL = float(os.getenv("PROBE_INTERVAL", "2.0"))
METRICS_SCRAPE_INTERVAL = float(os.getenv("METRICS_SCRAPE_INTERVAL", "0.5"))
# Vision routing: when an image request (base64/URL image block in the payload)
# arrives, force it onto the named vision backend (default the DGX Spark) so it
# never lands on a text-only 5090/3090 slot. Empty = no vision pinning.
VISION_BACKEND = os.getenv("VISION_BACKEND", "dgxsparx").strip()

# ---------------------------------------------------------------- backend model
@dataclass
class Backend:
    name: str
    url: str
    kind: str                 # "vllm" | "llama"
    priority: int
    cap: int                  # configured max active requests
    healthy: bool = True
    busy: int = 0             # backend-reported active requests
    inflight: int = 0        # requests this router has dispatched and not finished
    error: str = ""
    last_probe: float = 0.0
    _prev_healthy: bool = True      # for transition logging (healthy<->unhealthy)
    # rolling totals for the UI
    req_total: int = 0
    req_ok: int = 0
    req_err: int = 0
    bytes_in: int = 0
    bytes_out: int = 0
    req_active: int = 0

    @property
    def total_capacity(self) -> int:
        return self.cap

    @property
    def available(self) -> int:
        return max(0, self.cap - self.busy - self.inflight)


class Router:
    def __init__(self) -> None:
        self.backends: List[Backend] = [
            Backend(
                "red-pcv2-5090",
                os.getenv("RED5090_URL", "http://192.168.86.37:8006").rstrip("/"),
                os.getenv("RED5090_KIND", "vllm").lower(),
                1,
                int(os.getenv("RED5090_CAP", "2")),
            ),
            Backend(
                "databrick-3090",
                os.getenv("RED3090_URL", "http://host.docker.internal:8006").rstrip("/"),
                os.getenv("RED3090_KIND", "llama").lower(),
                2,
                int(os.getenv("RED3090_CAP", "1")),
            ),
            # DGX Spark (GB10) - high-throughput llama backend. Reached over the LAN
            # (no host-gateway needed). vLLM NVFP4->FP8 Flash-Next. Enabled only when SPARK_BACKEND_URL is set.
            *([
                Backend(
                    "dgxsparx",
                    os.getenv("SPARK_BACKEND_URL", "http://192.168.86.39:8006").rstrip("/"),
                    os.getenv("SPARK_KIND", "llama").lower(),
                    3,
                    int(os.getenv("SPARK_CAPACITY", "3")),  # Flash-Next qwen4exp llama.cpp: --parallel 3 (full 262K each)
                ),
            ] if os.getenv("SPARK_BACKEND_URL", "http://192.168.86.39:8006").strip() else []),
        ]
        self.by_name = {b.name: b for b in self.backends}
        self.sessions: Dict[str, Dict[str, Any]] = {}
        self.inflight_by_session: Dict[str, int] = defaultdict(int)
        self.lock = asyncio.Lock()
        # global request counters (all backends)
        self.g_req_total = 0
        self.g_req_inflight = 0
        self.g_bytes_in = 0
        self.g_bytes_out = 0
        self.g_routed_to = defaultdict(int)
        self._probe_task: Optional[asyncio.Task] = None

    # ---- probing -------------------------------------------------------
    async def _probe_vllm(self, b: Backend) -> None:
        """vLLM: active = running + waiting. Healthy if /health is 200."""
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(BACKEND_PROBE_TIMEOUT)) as c:
                h = await c.get(f"{b.url}/health")
                b.healthy = (h.status_code == 200)
                m = await c.get(f"{b.url}/metrics")
                if m.status_code == 200:
                    running = waiting = 0.0
                    for line in m.text.splitlines():
                        if line.startswith("vllm:num_requests_running "):
                            running = _last_float(line)
                        elif line.startswith("vllm:num_requests_waiting "):
                            waiting = _last_float(line)
                    b.busy = int(round(running + waiting))
                    b.error = ""
                else:
                    # can't read metrics; stay healthy, keep last busy
                    b.error = f"metrics {m.status_code}"
            b.last_probe = time.time()
        except Exception as exc:  # noqa
            b.healthy = False
            b.error = f"{type(exc).__name__}: {exc}"
            b.last_probe = time.time()
        self._log_transition(b)

    async def _probe_llama(self, b: Backend) -> None:
        """llama.cpp: active = slots currently processing. Healthy if /health ok."""
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(BACKEND_PROBE_TIMEOUT)) as c:
                h = await c.get(f"{b.url}/health")
                health_ok = (h.status_code == 200)
                s = await c.get(f"{b.url}/slots", params={"fail_on_no_slot": "0"})
                if s.status_code == 200:
                    slots = s.json()
                    if isinstance(slots, list):
                        b.busy = sum(1 for x in slots if x.get("is_processing"))
                    elif isinstance(slots, dict):
                        b.busy = int(slots.get("in_flight") or 0)
                    else:
                        b.busy = 0
                    b.error = ""
                else:
                    b.error = f"slots {s.status_code}"
                b.healthy = bool(health_ok)
            b.last_probe = time.time()
        except Exception as exc:  # noqa
            b.healthy = False
            b.error = f"{type(exc).__name__}: {exc}"
            b.last_probe = time.time()
        self._log_transition(b)

    def _log_transition(self, b: Backend) -> None:
        """Log only on a health STATE CHANGE (up->down or down->up), not every
        2 s probe. This is the single most useful line for 'why did the Spark
        drop out' -- it captures the exact ConnectError at the moment of the
        flip, which a steady-state probe never re-logs."""
        if b.healthy != b._prev_healthy:
            if b.healthy:
                LOG.info("backend %s UP (was down)", b.name)
            else:
                LOG.warning("backend %s DOWN: %s", b.name, b.error)
            b._prev_healthy = b.healthy

    async def probe(self) -> None:
        for b in self.backends:
            if b.kind == "vllm":
                await self._probe_vllm(b)
            else:
                await self._probe_llama(b)

    def _start_background_probe(self) -> None:
        async def _loop():
            while True:
                try:
                    await self.probe()
                except Exception as exc:  # noqa
                    LOG.warning("probe loop error: %s", exc)
                # scrape metrics more often for a snappy UI
                if time.time() - self._last_metrics_scrape > METRICS_SCRAPE_INTERVAL:
                    self._last_metrics_scrape = time.time()
                    for b in self.backends:
                        if b.kind == "vllm":
                            try:
                                await self._probe_vllm(b)
                            except Exception:  # noqa
                                pass
                await asyncio.sleep(PROBE_INTERVAL)
        if self._probe_task is None or self._probe_task.done():
            self._probe_task = asyncio.get_event_loop().create_task(_loop())

    # ---- session / routing -------------------------------------------
    async def _cleanup_sessions(self) -> None:
        now = time.monotonic()
        for sid in list(self.sessions):
            lease = self.sessions[sid]
            if lease["expires_at"] <= now and self.inflight_by_session.get(sid, 0) == 0:
                self.sessions.pop(sid, None)
                self.inflight_by_session.pop(sid, None)
                LOG.info("session lease expired session=%s", _hid(sid))

    def _can_use(self, b: Backend, sid: Optional[str]) -> bool:
        if not b.healthy:
            return False
        if b.available < 1:
            return False
        # a session already leased on this backend keeps its slot even if busy
        if sid and self.inflight_by_session.get(sid, 0) > 0 and \
                self.sessions.get(sid, {}).get("backend") == b.name:
            return True
        return True

    async def select(self, sid: Optional[str], force: Optional[str] = None,
                    vision: bool = False) -> Optional[Backend]:
        await self.probe()
        # Verbose pre-decision state dump: lets a "why did this land on X" question
        # be answered from the log alone (which backends were eligible, why).
        LOG.debug("select session=%s force=%s vision=%s backends=%s",
                  _hid(sid or "anon"), force, vision,
                  {b.name: {"healthy": b.healthy, "busy": b.busy,
                             "inflight": b.inflight, "avail": b.available,
                             "cap": b.cap, "err": b.error} for b in self.backends})
        async with self.lock:
            await self._cleanup_sessions()
            # VISION pin: an image request must reach the vision backend. If it's
            # healthy and has a free slot, commit there. Otherwise fall through to
            # sticky/priority so a busy vision backend still routes (the image block
            # is then the backend's concern); only a truly dead vision backend 500s
            # via the capacity path below.
            if vision and force:
                fb = self.by_name.get(force)
                if fb is not None and fb.healthy and self._can_use(fb, sid):
                    fb.inflight += 1
                    fb.req_active += 1
                    if sid:
                        self.sessions[sid] = {"backend": fb.name,
                                              "expires_at": time.monotonic() + SESSION_TTL_SECONDS}
                        self.inflight_by_session[sid] += 1
                    LOG.info("route session=%s backend=%s reason=vision-pinned avail=%s",
                             _hid(sid or "anon"), fb.name, fb.available)
                    return fb
                # The pin did NOT hold -- log WHY (this is the case that caused
                # image requests to spill onto text-only backends).
                reason = ("vision-backend-missing" if fb is None
                          else "vision-backend-unhealthy:" + (fb.error or "?") if not fb.healthy
                          else "vision-backend-full")
                LOG.warning("vision pin NOT honored: session=%s vision=%s reason=%s; "
                            "falling through to sticky/priority",
                            _hid(sid or "anon"), force, reason)
            # sticky: prefer the backend this session is already on, if still usable
            if sid:
                lease = self.sessions.get(sid)
                if lease:
                    b = self.by_name.get(lease["backend"])
                    if b and b.healthy and self._can_use(b, sid):
                        b.inflight += 1
                        b.req_active += 1
                        self.inflight_by_session[sid] += 1
                        lease["expires_at"] = time.monotonic() + SESSION_TTL_SECONDS
                        LOG.info("sticky route session=%s backend=%s", _hid(sid), b.name)
                        return b
                    LOG.debug("sticky backend %s not usable (healthy=%s avail=%s); "
                              "re-prioritizing session=%s",
                              lease["backend"], b.healthy if b else None,
                              b.available if b else None, _hid(sid))
            # strict priority order, first backend with capacity
            for b in sorted(self.backends, key=lambda x: x.priority):
                if self._can_use(b, sid):
                    b.inflight += 1
                    b.req_active += 1
                    if sid:
                        self.sessions[sid] = {"backend": b.name,
                                              "expires_at": time.monotonic() + SESSION_TTL_SECONDS}
                        self.inflight_by_session[sid] += 1
                    LOG.info("route session=%s backend=%s reason=priority-capacity avail=%s",
                             _hid(sid or "anon"), b.name, b.available)
                    return b
            LOG.warning("all backends at capacity; session=%s will 500", _hid(sid or "anon"))
            return None

    async def release(self, b: Backend, sid: Optional[str], ok: bool, nbytes_out: int) -> None:
        """Awaited (not fire-and-forget) so the in-flight decrement holds the
        same lock as select(); otherwise the last gen finishing can race a
        concurrent select() and let a request route to a backend that is now full."""
        async with self.lock:
            if b.inflight > 0:
                b.inflight -= 1
            if b.req_active > 0:
                b.req_active -= 1
            if ok:
                b.req_ok += 1
            else:
                b.req_err += 1
            b.bytes_out += nbytes_out
            if sid:
                self.inflight_by_session[sid] = max(0, self.inflight_by_session.get(sid, 0) - 1)
                if self.inflight_by_session.get(sid, 0) <= 0:
                    self.inflight_by_session.pop(sid, None)
                lease = self.sessions.get(sid)
                if lease and lease.get("backend") == b.name:
                    lease["expires_at"] = time.monotonic() + SESSION_TTL_SECONDS
            await self._cleanup_sessions()

    def on_dispatch(self, b: Backend, nbytes_in: int) -> None:
        b.req_total += 1
        b.bytes_in += nbytes_in
        self.g_req_total += 1
        self.g_bytes_in += nbytes_in
        self.g_routed_to[b.name] += 1
        self.g_req_inflight += 1

    def on_finish(self) -> None:
        if self.g_req_inflight > 0:
            self.g_req_inflight -= 1

    def snapshot(self) -> Dict[str, Any]:
        return {
            "now": int(time.time()),
            "policy": "strict-priority-dynamic-capacity",
            "probe_interval_s": PROBE_INTERVAL,
            "total_capacity": sum(b.cap for b in self.backends),
            "total_inflight_router": self.g_req_inflight,
            "requests_total_all": self.g_req_total,
            "backends": [
                {
                    "name": b.name,
                    "kind": b.kind,
                    "priority": b.priority,
                    "url": b.url,
                    "capacity": b.cap,
                    "busy": b.busy,
                    "router_inflight": b.inflight,
                    "available": b.available,
                    "healthy": b.healthy,
                    "error": b.error,
                    "req_total": b.req_total,
                    "req_ok": b.req_ok,
                    "req_err": b.req_err,
                    "bytes_in": b.bytes_in,
                    "bytes_out": b.bytes_out,
                    "last_probe_age_s": round(time.time() - b.last_probe, 2) if b.last_probe else None,
                }
                for b in self.backends
            ],
        }


def _last_float(line: str) -> float:
    try:
        return float(line.rsplit(" ", 1)[-1])
    except Exception:  # noqa
        return 0.0


def _hid(v: Optional[str]) -> str:
    return (v[:6] + "…") if v else "anon"


def _hget(headers: Dict[str, str], key: str) -> Optional[str]:
    """Case-insensitive header lookup. Starlette normalizes to lower-case, but a
    hand-rolled/proxied client can send `X-Api-Key` / `X-API-KEY` / `x-api-key`
    interchangeably; keying the auth off the exact case is what let a valid
    request 401 on session switch."""
    for k, v in headers.items():
        if k.lower() == key.lower():
            return v
    return None


def extract_session_id(headers: Dict[str, str], body: bytes) -> Optional[str]:
    # 1) explicit session headers (Claude Code sends CLAUDE_CODE_SESSION_ID as an
    #    X-* header when present; honor any of the known names, case-insensitively).
    for key in ("X-Qwen-Session-ID", "X-Claude-Session-ID", "X-Session-ID",
                "X-Conversation-ID"):
        val = _hget(headers, key)
        if val and val.strip() and val.strip().lower() not in {"", "no-key", "test", "none", "null", "local"}:
            return val.strip()
    # 2) the Authorization Bearer token is NOT a stable session id: it is the
    #    router API key (which we already used for auth), and a Claude Code
    #    *switch* to a new conversation can reuse/rotate it, so keying leases on
    #    it makes a brand-new session collide with the old one. Only fall back to
    #    it when it is genuinely a non-key token.
    auth = _hget(headers, "Authorization") or ""
    if auth.lower().startswith("bearer "):
        tok = auth[7:].strip()
        if ROUTER_API_KEY and tok.lower() == ROUTER_API_KEY.lower():
            tok = ""  # the API key itself: not a session
        if tok and tok.lower() not in {"no-key", "test", "none", "null", "local"}:
            return tok
    # 3) body-provided ids (Anthropic `metadata.session_id` / `conversation_id`).
    try:
        payload = json.loads(body.decode("utf-8"))
    except Exception:  # noqa
        return None
    if not isinstance(payload, dict):
        return None
    for key in ("session_id", "conversation_id"):
        if isinstance(payload.get(key), str) and payload[key].strip():
            return payload[key].strip()
    meta = payload.get("metadata")
    if isinstance(meta, dict):
        for key in ("session_id", "conversation_id"):
            if isinstance(meta.get(key), str) and meta[key].strip():
                return meta[key].strip()
    return None


_IMAGE_TYPES = frozenset({"image", "image_url", "image_base64"})


def _has_image(value: Any) -> bool:
    """Recursively search a decoded JSON payload for an image content block.
    Catches Anthropic ({type:"image"} and image* source blocks), OpenAI
    ({"type":"image_url"}), and llama.cpp ({content:[{image:...}]})."""
    if isinstance(value, dict):
        t = value.get("type")
        if isinstance(t, str) and t.lower() in _IMAGE_TYPES:
            return True
        # a base64/URL image under a "source" key (Anthropic) without a type
        src = value.get("source")
        if isinstance(src, dict) and isinstance(src.get("type"), str) and \
                src["type"].lower().startswith("image"):
            return True
        # explicit image field (llama.cpp / some OpenAI variants)
        if isinstance(value.get("image"), (str, dict)):
            return True
        for v in value.values():
            if _has_image(v):
                return True
    elif isinstance(value, (list, tuple)):
        for v in value:
            if _has_image(v):
                return True
    return False


def body_has_image(body: bytes) -> bool:
    """Cheap structural check: does the request body carry an image block?
    Used to force image requests onto the vision-capable backend (the DGX
    Spark) instead of a text-only 5090/3090 slot. Not a full parse for
    session id — just an answer to "is there a picture in here?"."""
    try:
        payload = json.loads(body.decode("utf-8"))
    except Exception:  # noqa
        return False
    # Only inspect chat-ish payloads; a 2 MB pure-text body still parses fast,
    # and the walk is bounded by the body itself.
    return _has_image(payload)


def _auth_ok(headers: Dict[str, str]) -> bool:
    if not ROUTER_API_KEY:
        return True
    # x-api-key (case-insensitive)
    x = _hget(headers, "x-api-key")
    if x and x.strip() == ROUTER_API_KEY:
        return True
    # Authorization: Bearer <key> | Basic ... (UI) | <raw key> (Anthropic style)
    auth = _hget(headers, "authorization") or ""
    if auth.startswith("Bearer "):
        return auth[7:].strip() == ROUTER_API_KEY
    if auth.startswith("Basic "):
        return True  # UI may use Basic; backends use the router key
    return auth.strip() == ROUTER_API_KEY


app = FastAPI(title="qwen38-gpu-router")
state = Router()
state._last_metrics_scrape = 0.0


@app.on_event("startup")
async def _startup() -> None:
    await state.probe()
    state._start_background_probe()
    LOG.info("router up: %s", [(b.name, b.kind, b.cap) for b in state.backends])
    LOG.info("effective config: LOG_LEVEL=%s VISION_BACKEND=%s PROBE_INTERVAL=%ss "
             "SESSION_TTL=%ss MAX_REQ=%ss log_ring=%d",
             os.getenv("LOG_LEVEL", "INFO"), VISION_BACKEND or "(none)",
             PROBE_INTERVAL, SESSION_TTL_SECONDS, MAX_REQUEST_SECONDS, LOG_RING_MAX)


@app.get("/health")
async def health() -> JSONResponse:
    await state.probe()
    all_at_cap = all(b.available <= 0 for b in state.backends)
    return JSONResponse({
        "status": "ok",
        "any_capacity": not all_at_cap,
        "backends": [
            {"name": b.name, "healthy": b.healthy, "available": b.available, "capacity": b.cap}
            for b in state.backends
        ],
    })


@app.get("/router/status")
async def router_status() -> JSONResponse:
    return JSONResponse(state.snapshot())


@app.get("/metrics")
async def router_metrics() -> JSONResponse:
    # legacy alias (returns JSON)
    return JSONResponse(state.snapshot())


def _render_metrics() -> str:
    """Render the current router snapshot as Prometheus text exposition."""
    snap = state.snapshot()
    lines: List[str] = []
    t = snap.get("now", 0)

    def _g(name: str, helpstr: str, value: Any, labels: Optional[Dict[str, str]] = None):
        lab = ""
        if labels:
            lab = "{%s}" % ", ".join(f'{k}="{v}"' for k, v in labels.items())
        lines.append(f"# HELP {name} {helpstr}")
        lines.append(f"# TYPE {name} gauge")
        v = value
        if isinstance(v, float) and v.is_integer():
            v = int(v)
        lines.append(f"{name}{lab} {v} {int(t)}")

    _g("qwen38_router_total_capacity", "Total live capacity across all backends (sum of per-backend caps)",
       snap.get("total_capacity", 0))
    _g("qwen38_router_total_inflight", "Requests currently in-flight on the router",
       snap.get("total_inflight_router", 0))
    _g("qwen38_router_requests_total_all", "Total requests handled by the router since start",
       snap.get("requests_total_all", 0))
    for b in snap.get("backends", []):
        lbl = {"backend": str(b.get("name", "unknown")), "priority": str(b.get("priority", 0))}
        _g("qwen38_router_backend_capacity", "Configured capacity (slots) for this backend", b.get("capacity", 0), lbl)
        _g("qwen38_router_backend_busy", "Busy slots reported by the backend", b.get("busy", 0), lbl)
        _g("qwen38_router_backend_router_inflight", "Router in-flight requests to this backend", b.get("router_inflight", 0), lbl)
        _g("qwen38_router_backend_available", "Available slots (capacity - busy - inflight)", b.get("available", 0), lbl)
        _g("qwen38_router_backend_healthy", "1 healthy, 0 down (from /health probe)", 1 if b.get("healthy") else 0, lbl)
        _g("qwen38_router_backend_requests_total", "Total proxied requests to this backend", b.get("req_total", 0), lbl)
        _g("qwen38_router_backend_requests_ok", "Successful (2xx/3xx) proxied requests", b.get("req_ok", 0), lbl)
        _g("qwen38_router_backend_requests_err", "Failed (non-2xx/3xx) proxied requests", b.get("req_err", 0), lbl)
        _g("qwen38_router_backend_bytes_in", "Total bytes read from clients for this backend", b.get("bytes_in", 0), lbl)
        _g("qwen38_router_backend_bytes_out", "Total bytes written to clients for this backend", b.get("bytes_out", 0), lbl)
        _g("qwen38_router_backend_last_probe_age_s", "Seconds since the last successful backend probe", b.get("last_probe_age_s", 0), lbl)
    return "\n".join(lines) + "\n"


@app.get("/router/metrics")
async def router_metrics_prom() -> PlainTextResponse:
    return PlainTextResponse(_render_metrics(), media_type="text/plain; version=0.0.4; charset=utf-8")


@app.get("/router/logs")
async def router_logs(request: Request) -> PlainTextResponse:
    """Last N lines of the router's own log (in-memory ring). Query:
        GET /router/logs?lines=500
    Returns plain text (same format as `docker logs`). Lets you tail the
    router from the router itself -- no SSH, no `docker logs`. The on-disk
    json-file (max-size/max-file) keeps the full rolling history.
    Cap the value at LOG_RING_MAX so the query can't exceed the ring."""
    try:
        n = int(request.query_params.get("lines", "200"))
    except ValueError:
        n = 200
    lines = tail_lines(n)
    return PlainTextResponse(
        ("; ".join(lines) if False else "\n".join(lines)) + "\n",
        media_type="text/plain; charset=utf-8")


# ---------------------------------------------------------------- contract
# The 5090 (vLLM) and the 3090 (llama.cpp) expose DIFFERENT /v1/models shapes.
#   vLLM : {id, object:"model", created, owned_by:"vllm", root, max_model_len, permission[...]}
#   llama: {id, object:"model", aliases, tags, owned_by:"llamacpp", meta:{n_ctx,n_vocab,...}}
# The router proxies whichever backend answers, so the *client* would see the
# contract flip depending on which GPU it landed on. To give Claude Code one
# stable contract (the 5090's vLLM/OpenAI shape, which is what it already
# trusts), the router serves a single unified /v1/models itself.
def _unified_models() -> Dict[str, Any]:
    import time as _t
    now = int(_t.time())
    return {
        "object": "list",
        "data": [{
            "id": "qwen3.8",
            "object": "model",
            "created": now,
            "owned_by": "vllm",
            "root": "/models/Qwen3.8-Flash-Next-FP8",
            "parent": None,
            "max_model_len": 262144,
            "permission": [{
                "id": "modelperm-router",
                "object": "model_permission",
                "created": now,
                "allow_create_engine": False,
                "allow_sampling": True,
                "allow_logprobs": True,
                "allow_search_indices": False,
                "allow_view": True,
                "allow_fine_tuning": False,
                "organization": "*",
                "group": None,
                "is_blocking": False,
            }],
        }],
    }


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
                name="proxy")
async def proxy(request: Request, path: str) -> StreamingResponse:
    headers = dict(request.headers)
    # machine/ops endpoints (key not required) -> the UI proxies these
    if path in ("health", "router/status", "router/health", "router/metrics"):
        if path in ("health", "router/health"):
            return await health()
        return await router_status()

    if not _auth_ok(headers):
        return JSONResponse({"error": "unauthorized: missing or invalid API key"}, status_code=401)

    # Unified contract: model discovery is answered by the router itself, not
    # the backend that happens to be free, so /v1/models never changes shape
    # between the 5090 and the 3090.
    if path == "v1/models" or path.endswith("/v1/models"):
        return JSONResponse(_unified_models())

    body = await request.body()
    sid = extract_session_id(headers, body)
    # Pin image requests to the vision-capable backend (DGX Spark) so a base64/URL
    # image never lands on a text-only 5090/3090 slot. Off when VISION_BACKEND
    # is unset, or when the payload carries no image block.
    is_vision = bool(VISION_BACKEND) and body_has_image(body)
    LOG.debug("request %s %s/%s session=%s body=%sB vision=%s",
              request.method, path, request.url.query or "-", _hid(sid or "anon"),
              len(body), is_vision)
    backend = await state.select(sid, force=VISION_BACKEND if is_vision else None,
                                 vision=is_vision)
    if is_vision:
        LOG.info("vision request detected; pinned session=%s to %s",
                 _hid(sid or "anon"), VISION_BACKEND)
    if backend is None:
        return JSONResponse(
            {"error": "queued: all backends at max capacity",
             "type": "capacity_exhausted",
             "backends": [{"name": b.name, "available": b.available, "capacity": b.cap}
                          for b in state.backends]},
            status_code=500)

    state.on_dispatch(backend, len(body))
    url = f"{backend.url}/{path}"
    if request.url.query:
        url = f"{url}?{request.url.query}"
    # Strip the client's own auth header: it carries the ROUTER key, and
    # backends that do strict bearer validation (vLLM/ds4) reject an
    # Authorization that isn't the token they expect. The router has already
    # authenticated, so the backends never need to re-check it.
    fwd_headers = {k: v for k, v in headers.items()
                   if k.lower() not in {"host", "content-length", "connection",
                                        "accept-encoding", "x-forwarded-for",
                                        "x-api-key", "authorization"}}
    fwd_headers["connection"] = "keep-alive"

    nbytes_out = 0
    client = httpx.AsyncClient(timeout=httpx.Timeout(MAX_REQUEST_SECONDS))
    stream_ctx = client.stream(request.method, url, headers=fwd_headers, content=body)
    response = await stream_ctx.__aenter__()
    status_code = response.status_code

    async def _gen():
        nonlocal nbytes_out
        try:
            async for chunk in response.aiter_bytes():
                nbytes_out += len(chunk)
                yield chunk
        finally:
            try:
                await stream_ctx.__aexit__(None, None, None)
                await client.aclose()
            except Exception:  # noqa
                pass
            await state.release(backend, sid, ok=(200 <= status_code < 400), nbytes_out=nbytes_out)
            state.on_finish()
            LOG.info("done session=%s backend=%s status=%s out=%sB",
                     _hid(sid or "anon"), backend.name, status_code, nbytes_out)

    out_headers = {k: v for k, v in response.headers.items()
                   if k.lower() not in {"content-encoding", "transfer-encoding", "connection"}}
    return StreamingResponse(_gen(), status_code=status_code, headers=out_headers)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=ROUTER_HOST, port=ROUTER_PORT)
