# AGENTS.md — how to work in this repo

This is a **lab GPU-fleet repo, not a product**. It describes a working
inference cluster (Qwen3.8-27B + a 180B MoE vision model) on three machines,
fronted by a custom Go router. The YAMLs are the source of truth that deploys
through Portainer; the launchers + `.env` point a client (Claude Code) at the
router.

## The ground rules

- **Secrets live in `.env` (gitignored).** Never commit `.env` or any real
  password / IP / API key. Committed YAMLs, scripts, and launchers read
  `${VAR}` / `%VAR%` / `$VAR` from `.env`. `.env.example` is the placeholder
  template — it *may* be committed.
- **`backends/` + `router/` are the deploy source of truth.** Edit the YAML
  there to change a stack, then redeploy via the Portainer API (delete by name
  + recreate). `archive/` is history — don't edit it.
- **`router-legacy/` is the retired Python router** (kept for reference). The
  live router is the Go one in `router/`.
- **The 5090 vLLM is "untouched."** Don't change its flags; the router reads
  only its `/health` + `/metrics`.

## Build / test the router

```
cd router
go test ./...      # capacity, routing, streaming, api
go vet ./...
```

Rebuild the image + redeploy + validate: `router/scripts/build.sh`,
`portainer-deploy.sh`, `validate.sh` (Phase F 1-14).

## Port contracts (permanent — a runtime outside its range must not route)

| Range | Runtime | This fleet |
|---|---|---|
| 8000-8009 | Router | 8001 (8000 = Portainer) |
| 8100-8199 | llama.cpp | 3090 :8101 |
| 8200-8299 | vLLM | 5090 :8201 |
| 8300-8399 | SGLang | (reserved) |
| 8400-8499 | Vision | Spark :8401 |
| 8500-8599 | Embeddings | (reserved) |
| 9000-9099 | Metrics | Portainer :9000, Prometheus :9090 |

## Self-contained projects (leave them alone)

- `llmbench/` — standalone benchmark tool.
- `video/` — standalone Vite/React fleet-animation (its source intentionally
  carries a LAN IP). `node_modules`/`dist` are gitignored.
- `monitoring/` — Prometheus + Grafana config; the Grafana 13 write gotcha is
  documented in `monitoring/README.md`.

## When adding a backend

1. Add a YAML under `backends/<device>/` following the existing shape.
2. Seed the router: append an endpoint to `router/config/router.yaml` *and* to
   the `ROUTER_ENDPOINTS_JSON` in `router/llm-router-stack.yaml` (config-only,
   no rebuild — the stack injects it at boot).
3. Assign a port inside the correct contract; set `runtime.type` so it matches
   the range (a vision endpoint on 8401 uses `type: vision`, not `llama.cpp`).
4. Redeploy the router stack (delete + recreate), then `router/scripts/validate.sh`.

## Conventions

- No emojis in docs.
- Full descriptions + the deep architecture live in `README.md` and `docs/`.
- Keep host IPs out of committed code where a `${HOST_*}` exists; docs may name
  hosts concretely.
