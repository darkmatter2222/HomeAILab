# qwen38 GPU Router + Live Traffic UI

Two Portainer stacks (endpoint 3 / Databrick) that put a **priority ingress**
in front of the two Qwen3.8-27B backends and show **live traffic** for them.

| Stack (Portainer)  | Container            | Port | Role |
|--------------------|----------------------|------|------|
| `qwen38-gpu-router`| `qwen38-gpu-router`  | 8010| FastAPI router / ingress (what Claude Code points at) |
| `qwen38-router-ui` | `qwen38-router-ui`   | 8090| Real-time traffic dashboard (HTTP basic auth) |

Neither stack touches the 5090 — the router only *reads* its `/health` and
`/metrics` and proxies requests to it.

## Routing policy (dynamic)

Backends, strict priority order:

1. **RedPCv2 RTX 5090** — vLLM, `192.168.86.37:8006`, capacity `RED5090_CAP` (default **2** = its `--max-num-seqs`).
2. **Databrick RTX 3090** — llama.cpp, `host.docker.internal:8006`, capacity `RED3090_CAP` (default **1** = `--parallel 1`).

Per request the router:

1. **Probes live capacity** (every `PROBE_INTERVAL` s, default 2 s):
   - vLLM → `vllm:num_requests_running + vllm:num_requests_waiting` from `/metrics`.
   - llama → count of `/slots` entries with `is_processing: true`.
   - **Plus** the router's own **in-flight** count (requests it dispatched and
     has not finished) — this is the authoritative occupancy signal. vLLM 0.27.1
     does not populate `num_requests_running`/`waiting` reliably, so in-flight is
     what actually gates capacity.
2. **Routes by priority**: a backend is usable when `cap - busy - inflight >= 1`
   and it is healthy. It tries priority-1 (5090) first; if that is at live
   capacity it spills to priority-2 (3090).
3. **503 ONLY when every backend is at its live max** (i.e. total in-flight ==
   total capacity). Any other outcome is a normal 2xx/5xx from the backend.
4. **Sticky sessions**: a session id (from `X-Claude-Session-ID`,
   `X-Session-ID`, `X-Conversation-ID`, the Bearer token, or body
   `session_id`/`conversation_id`/`metadata.*`) is pinned to the backend it
   started on, so a conversation keeps the GPU that holds its KV/prefix cache.

The 3090 is reached from the router container via `host.docker.internal`
(added with `extra_hosts: host.docker.internal:host-gateway`).

## API key (Claude Code)

One key, set in the router stack env `ROUTER_API_KEY` (real value in `.env`):

```
<ROUTER_API_KEY from .env>
```

Accepted as `x-api-key`, `Authorization: Bearer <key>`, or raw
`Authorization: <key>` (Anthropic style). No key → 401.

Point **Claude Code** at the router (OpenAI-compatible base URL is `:8010`,
Anthropic-compatible `/v1/messages` also proxied):

```
# OpenAI-style
OPENAI_BASE_URL=http://<databrick>:8010/v1
OPENAI_API_KEY=<ROUTER_API_KEY from .env>
# Anthropic-style
ANTHROPIC_BASE_URL=http://<databrick>:8010
ANTHROPIC_API_KEY=<ROUTER_API_KEY from .env>
```

The model name the backends serve is `qwen3.8`.

## Live-traffic dashboard (rebuilt 2026-08-29) — `qwen38-router-status`, `:8091`

The old token-login UI (`qwen38-router-ui`, `:8090`) and its token-login
rewrite were retired. They're replaced by a single, robust dashboard:

| | |
|---|---|
| **URL** | `http://192.168.86.48:8091/` |
| **username / password** | **`fleet`** / **(in `.env` as `UI_STATUS_*`; also in the stack env `UI_USER`/`UI_PASS`)** |
| **Auth** | classic HTTP **basic auth** — the browser attaches `Authorization: Basic` to the page *and* to each 2 s poll, so there is no token login to wedge |
| **Stack / source** | `qwen38-router-status-v1.yaml` · page `qwen3.8-27b/router/router-status.html` (bind-mounted to `/home/darkmatter2222/qwen38-router/router-status.html`) |

It polls the router's open `/router/status` every 2 s (the stack proxies it,
so the browser never needs the GPU router key) and shows, live:
- **3 device cards** (RedPCv2 5090 · vLLM, Databrick 3090 · llama, DGX Spark ·
  llama) — priority order, live capacity, busy (backend-reported) vs
  in-flight (router-dispatched) stacked bar, free slots, READY/FULL/DOWN.
- **Hero stats** — total capacity, in-flight now, all-time request count,
  requests in the last 30 s.
- **Request stream (last 30 s)** — a per-device requests/s line chart (delta of
  `req_total` between polls, so only real movement draws a point) and a
  newest-activity feed (new requests per device per 2 s tick, no idle spam).
- Light/dark theme, self-contained (no pip deps, `python:3.11-slim` + stdlib
  HTTP server). It reads only the router's open endpoint, so **traffic keeps
  flowing on `:8010` while the dashboard is (re)deployed.**

## (Retired) old UI credentials — `:8090`

`http://<databrick>:8090/` → username **`operator`** / password **(in `.env` as `UI_UI_PASS`)**
(the basic-auth pair on the old `qwen38-router-ui` stack, env `UI_USER`/
`UI_PASS`). That stack has been deleted; use `:8091` above.

## Endpoints

| Path | Auth | Purpose |
|------|------|---------|
| `:8010/health` | open | router + per-backend health/availability |
| `:8010/router/status` | open | full machine snapshot (UI data source) |
| `:8010/<anything>` | API key | proxied to the chosen backend |
| `:8090/` | basic auth | live traffic dashboard |

## Re-tune / edit

- **Change backends or capacity**: edit the router stack's `RED5090_*` /
  `RED3090_*` / `*_CAP` env in Portainer, redeploy.
- **Change the key**: edit `ROUTER_API_KEY`, redeploy.
- **UI creds**: edit `UI_USER`/`UI_PASS`, redeploy the UI stack.
- **Router source** lives at `/home/darkmatter2222/qwen38-router/router.py`
  (bind-mounted into the container; copied in at startup). Edit there and
  restart the container, or redeploy the stack.
- Re-deploy a stack: `bash qwen3.8-27b/redeploy.sh` (delete + recreate via the
  Portainer API).

## Verified behavior (2026-08-22)

- 5090-first routing (fingerprint `vllm-0.27.1…`).
- 5090 full (2 in-flight) → 3rd request **spilled to the 3090** (fingerprint
  `b10573…`, the llama server).
- 3090 also full (total in-flight 3 = total capacity) → 4th request **503
  `capacity_exhausted`**.
- All gens finish → capacity recovers (in-flight back to 0, `avail` restored).
- No key → 401. UI 200 with `operator/<UI_UI_PASS>`, 401 without. 5090's own
  `/health` still 200 (untouched).
