# LLM Router — Deployment Report (handoff §21)

**Date:** 2026-08-30
**Status:** ✅ Deployed, validated, live (deterministic 5090 router)

## What was built & deployed

A custom **Go** LLM router (`llm-router`), single process, no DB/Redis.
Control plane (async discovery/health/lease-repair) is fully separated from the
hot data plane (classify → in-memory filter → atomic static-capacity reserve →
stream-proxy → release-on-true-stream-end).

| Item | Value |
|---|---|
| Source | `llm-router/` (Go 1.24, stdlib + `gopkg.in/yaml.v3`) |
| Image | `local/llm-router:1.0.0` (scratch, **9.93 MB**) on Databrick |
| Stack | Portainer `llm-router` **id 93**, endpoint **3**, status 1, path `/data/compose/93` |
| Container | `llm-router` — Up, **healthy**, `0.0.0.0:8001->8001` |
| Public URL | `http://192.168.86.48:8001` |
| Seeded endpoint | `rtx5090-qwen38-262k-01` → `192.168.86.37:8201` (vLLM 0.27.1, qwen3.8, 262144) |
| Static capacity | **1** (router-side, handoff mandate; vLLM itself untouched at `--max-num-seqs 2`) |
| Strategy | deterministic priority, prefer-smallest-sufficient context, static atomic reservations |
| Public alias | `local-coding` → backend `qwen3.8` (router translates request + response) |

## Rollback
`claude-direct5090.bat` — points `ANTHROPIC_BASE_URL` at `http://192.168.86.37:8201`
directly (model `qwen3.8`, no router). Normal mode: `claude-router.bat`.

## Phase F validation (all pass, through `:8001`)

| # | Test | Result |
|---|---|---|
| 1 | `GET /health` | ✅ `{"healthy":1,"total":1}` |
| 2 | `GET /v1/models` | ✅ advises `local-coding` (alias) + `qwen3.8` (backend) |
| 3 | `POST /v1/chat/completions` (non-stream) | ✅ 200, `content:"OK"`, routed to qwen3.8 |
| 4 | streaming (`stream:true`) | ✅ 25 SSE chunks, clean `data: [DONE]` |
| 5 | Anthropic `POST /v1/messages` | ✅ 200, `type:"message"` |
| 6 | `POST /v1/messages/count_tokens` | ✅ `{"input_tokens":27}` (N>0) |
| 7 | tools | ✅ 200, `finish_reason:"tool_calls"`, real `get_weather` call |
| 8 | thinking-off | ✅ no `thinking`/`reasoning` content in responses |
| 9 | capacity=1 hold | ✅ while held inflight=1, 2nd request → **503 `CAPACITY_FULL`/`capacity_exhausted`** |
| 10 | release on complete | ✅ inflight back to 0 after the held request finishes |
| 11 | drain / undrain | ✅ drain → new reqs 503-rejected; undrain → 200 again |
| 12 | release on client-cancel | ✅ kill client mid-stream → inflight → 0 |
| 13 | health-removal (drain) | ✅ covered by T11; endpoint flips draining/healthy correctly |
| 14 | concurrency unit test | ✅ 100 goroutines, capacity-1 → exactly 1 reserved, 99 full, no leak; lease watchdog reaps |

`go vet ./...` clean, `go test ./...` green (capacity, routing, streaming, api).

## Live-fleet notes found during deploy
- **5090 host = this machine (192.168.86.37 / RedPCv2's LAN IP)**, running the
  `qwen38-vllm-5090` container in local WSL (host port **8201** → container 8006).
- **Firewall gap fixed:** the host's Windows Firewall only allowed inbound **8006**;
  added `WSL Docker vLLM (8201)` (TCP 8201, Profile Any) so Databrick can reach
  `.37:8201`. This matches the manifest's vllm port contract (8200–8299) — "that is law."
- The old `claude-cluster.bat` (3-backend dynamic router on :8010) is **superseded**
  by `claude-router.bat` (deterministic Go router on :8001).

## Known caveat
The router's `ROUTER_UPSTREAM_CONNECT_TIMEOUT_MS=250` (handoff constant) is a touch
tight for the WSL-mirrored NAT path Databrick→.37:8201; one T7 attempt flaked to a
pre-stream 502 and succeeded on immediate retry. Bump to ~1000ms if the NAT is
consistently slow. The health probe (750ms) is unaffected.

## Commands
- **Rebuild:** `cd llm-router && scripts/build.sh` (scp → `docker build -t local/llm-router:1.0.0`)
- **Redeploy:** delete stack + `scripts/portainer-deploy.sh` (Portainer API, endpoint 3)
- **Validate:** `scripts/validate.sh` (Phase F 1–14 against `:8001`)
- **Switch Claude Code:** run `claude-router.bat`; rollback `claude-direct5090.bat`
