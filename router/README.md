# llm-router — ultra-fast local LLM router (Go)

A single-process, control-plane/data-plane-separated router for a local GPU
inference fleet. The hot path reads an in-memory routing table and streams
directly to the chosen endpoint — **no** per-request health, GPU, Prometheus,
Docker, Portainer, or model-introspection call.

> `DISCOVER SLOWLY / VALIDATE STRICTLY / STORE LOCALLY / ROUTE IMMEDIATELY /
> COUNT ATOMICALLY / STREAM DIRECTLY`

## Layout

```
cmd/router/         main: wires control plane + data plane, health-probe subcommand
internal/
  config/           YAML + ROUTER_* env overrides + boot-time hot-path assertions
  manifest/         Endpoint/Signature/Manifest, port-contract validation
  capacity/         per-endpoint atomic CAS reserve/release + lease map + ReapLeases
  registry/         Registry + RoutingTable (RCU swap) + capability indexes
  routing/          Classify, RequiredContext, deterministic Select
  health/           async health worker (UNKNOWN/HEALTHY/SUSPECT/UNHEALTHY)
  discovery/        rescan + lease-repair watchdog
  proxy/            lazy-body streaming reverse proxy + pre-stream failover
  api/              /v1/*, /admin/*, /health, /metrics, /router/status
  telemetry/        hand-rolled Prometheus text + routing-decision logs
config/router.yaml  in-repo source of truth (5090 seed)
llm-router-stack.yaml  Portainer deploy (endpoint 3, port 8001)
scripts/            build.sh, portainer-deploy.sh, validate.sh
tests/              go test ./...
```

## Build & deploy

```bash
./scripts/build.sh            # scp source to Databrick, docker build local/llm-router:1.0.0
./scripts/portainer-deploy.sh # Portainer API: create stack on endpoint 3 (Databrick)
```

## Public API (bound 0.0.0.0:8001)

```
GET  /health
GET  /metrics
GET  /v1/models
POST /v1/chat/completions
POST /v1/responses
POST /v1/messages
POST /v1/messages/count_tokens
GET  /router/status
GET  /admin/{hosts,endpoints,routing-table,requests,config}
POST /admin/discovery/rescan
POST /admin/endpoints/{id}/{enable,disable,drain,undrain}
```

Public model alias: `local-coding` (maps to backend `qwen3.8`).

## Seeded endpoint

`rtx5090-qwen38-262k-01` → `192.168.86.37:8201` (vLLM 0.27.1, `qwen3.8`,
262K, static capacity **1**, vision=false, tools=true, thinking=false,
priority 10). 3090 / DGX Spark are added later (Phase G) — the host list and
port-contract scan are append-only.

## Rollback

```bash
# Stop the router stack only; the 5090 vLLM is untouched.
ssh databricks 'docker stop llm-router'
# Or remove the stack via Portainer (endpoint 3).
```
The direct-5090 bypass (`http://192.168.86.37:8201`) stays available until the
router passes all Phase F acceptance tests.
