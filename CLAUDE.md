# modeloptimizer — Qwen3.8-27B GPU Fleet

Multi-host inference fleet for **Qwen3.8-27B (abliterated / "Uncensored")** plus a
180B MoE vision model, deployed **only via Portainer stacks** (the YAMLs here are
the source of truth you maintain in the Portainer UI). Every download is capped at
**25 MiB/s**.

**The primary router is now the Go LLM router** (`router/`, `:8001`, deterministic
5090 → 3090 → Spark). The old Python 3-backend router (`:8010`) is **archived** in
`router-legacy/`.

All hosts, creds, and Portainer endpoints live in `.env` (SSH key-based, gitignored):

- **Databrick** `.48` — Portainer server + RTX 3090 (endpoint **3**, the router host).
- **DGX Spark** `.39` — NVIDIA GB10, 122 GiB (endpoint **4**).
- **RedPCv2** `.37` — RTX 5090, vLLM, local WSL Docker (endpoint **5**).

Portainer API: `POST :9000/api/auth` (user in `.env`) → JWT →
`POST /api/endpoint/<id>/stacks/create/standalone/string` (create+deploy in one
call), `DELETE /api/stacks/<id>?endpointId=N`. Re-deploy any stack = delete by
name + recreate (upsert does not recreate on env-only changes).

**Monitoring** — Prometheus + Grafana on the DGX Spark; editable copies in
`monitoring/` (`prometheus.yml` + the `adrsc9f` dashboard, with a `device` filter).
Reload via `POST http://<spark>:9090/-/reload`. Grafana 13 stores dashboards in
Unified Storage — see `monitoring/README.md`.

---

## 1. The Go router (primary) — `router/`, Databrick endpoint 3, port 8001

Single Go 1.24 binary (stdlib + `gopkg.in/yaml.v3`), scratch image
`local/llm-router:1.0.0`, deployed via `router/llm-router-stack.yaml`.

- **Deterministic cascade:** 5090 (prio 10, cap 1) → 3090 (prio 20, cap 1) →
  Spark (prio 30, cap 3, **vision-pinned**).
- **Public alias** `local-coding` → backend `qwen3.8` (router rewrites request +
  response `model`).
- **Static atomic capacity.** At max, controlled **503 `CAPACITY_FULL`**.
  Release-on-true-stream-end; pre-stream-only failover (no migration once bytes
  flow). No health check / GPU poll / Prometheus query in the hot path.
- **Endpoints** (3): `:8201` vLLM, `:8101` llama.cpp, `:8401` Flash-Next (vision,
  runtime type `vision` to match the 8400-8499 contract).
- **Spark caveat:** ~60-120 s cold TTFT (SSD-PLE prefill). `upstream.
  response_header_timeout_ms: 180000` so the slow prefill can emit a first byte.
  Connect stays 250 ms.
- **Build/test:** `cd router && go test ./...` · `go vet ./...`. Rebuild image
  (`router/scripts/build.sh`), redeploy (`router/scripts/portainer-deploy.sh`),
  validate (`router/scripts/validate.sh`, Phase F 1-14).
- **Report:** `router/DEPLOYMENT_REPORT.md`.

**Rollback:** `launchers/claude-direct5090.bat` (direct `:8201`, model `qwen3.8`,
no router).

---

## 2. RTX 3090 — `qwen38-27b-3090` (Databrick, endpoint 3)

YAML: `backends/rtx3090/qwen38-27b-3090-v2.yaml` (the live one).

- **Engine:** `ghcr.io/ggml-org/llama.cpp:server-cuda12`. **Model:**
  `Qwen3.8-27B-Uncensored-Q4_K_M.gguf` (fused, MTP head built in), 16.8 GiB.
- **Why 262K fits 24 GB:** Qwen3.8 is hybrid linear+full attention (16/64 layers
  full-attention) → 262K KV is tiny (q4_0 ~4 GiB). q4 is the max precision that
  fits.
- **Speed:** built-in **MTP spec decode** (`--spec-type draft-mtp
  --spec-draft-n-max 3`, no separate drafter). ~60 tok/s decode (1.47x the 40.6
  no-spec baseline), prefill ~1.15-1.3k tok/s, TTFT ~0.2 s, 262K verified.
- Re-tune: `qwen3.8-27b/tune.sh`, `prefilltest.sh`, `bench.py`. Redeploy:
  `qwen3.8-27b/redeploy.sh`. Writeup: `docs/RESULTS.md`.

---

## 3. RTX 5090 — RedPCv2 (endpoint 5, port 8201) — *untouched*

- **Engine:** vLLM (`vllm/vllm-openai:v0.27.1`), OpenAI + Anthropic APIs.
- **Capacity:** `--max-num-seqs 2` (router-side static capacity = 1; do not touch
  the vLLM). Reached at `http://<.37>:8201`. The router only reads `/health` +
  `/metrics` and proxies to it.
- **Firewall note:** the 5090 host is RedPCv2's own WSL Docker; a Windows
  Firewall rule `WSL Docker vLLM (8201)` (TCP 8201) lets Databrick reach it
  (the old rule only allowed 8006). Port contract: vllm 8200-8299 — keep 8201.
- Reference YAML: `backends/rtx5090/RTX5090DSAMPL.yaml`.

---

## 4. DGX Spark (GB10 / Blackwell) — endpoint 4

Two 27B builds + the 180B vision model:

| YAML (in `backends/dgxspark/`) | build | model | engine |
|---|---|---|---|
| `qwen38-27b-dgxsparx-v2-nvfp4.yaml` (deployed) | NVFP4 | ModelOpt NVFP4 (MTP-grafted) | vLLM `vllm-arm64-cu13-0.25.1` |
| `qwen38-27b-dgxsparx-v1.yaml` | Q4_K_M | fused-MTP GGUF | llama.cpp `server-cuda` |
| `qwen38-flashnext-dgxsparx-v3-ds4ssdple.yaml` | ds4 SSD-PLE | Qwen3.8-Flash-Next 180B MoE | Baekpica ds4 (vision, 3 slots) |

**NVFP4 (deployed):** same NVFP4-ModelOpt weights the 5090 runs. Flags:
`--quantization modelopt_fp4 --kv-cache-dtype fp8 --attention-backend FLASHINFER
--gpu-memory-utilization 0.85` (GB10 runs a desktop, so 0.92 OOMs), thinking OFF,
`--max-model-len 262144 --max-num-seqs 16`. Aggregate ~165 tok/s @16 wide. MTP
spec decode is the ~1.56x single-stream win (19.5 tok/s, ~60% accept). Sweep:
`qwen3.8-27b/sweep_spark_vllm.sh` (vLLM), `sweep_spark.sh` (llama).

**Flash-Next 180B MoE:** native vision (embedded Qwen tower, no mmproj), ~60-120 s
cold TTFT. The router pins image requests to it (only `vision:true` endpoint).

---

## 5. Legacy Python router — `router-legacy/` (archived, :8010)

The retired 3-backend dynamic router (5090 cap2 → 3090 cap1 → Spark cap16) + the
live-traffic dashboard. Source: `router-legacy/router.py`, `ui.html`,
`router-status.html`. See `router-legacy/README.md`. Superseded by the Go router;
kept for reference + the `claude-cluster.bat` launcher.

---

## 5.5 Claude Fleet Deck — `deck/` (Stream Deck Mini, local)

A **custom Elgato Stream Deck plugin** (Node, self-contained like `router/`/`video/`)
that makes the Stream Deck Mini the notification bar for every local Claude Code
agent: launch, monitor (RAG running/waiting/idle), and focus. No cloud.

- **Layout:** 6-key Mini. Top row = 3 identical "launch a session" keys (idle);
  press → project menu (pages of 5 projects + a nav key, auto-return to main after
  5 s idle). Bottom row = keep-for-later spare keys.
- **Config:** `deck/projects.json` (`{alias, path, bat}` — the `homeai` example
  points at this repo + `launchers/claude-router.bat`). Auto-detected manual
  sessions land in `deck/projects.auto.json` (never clobbers the hand-written file).
- **Session discovery** reads `~/.claude/sessions/` (alive-pid filter, recycled-pid
  guard) and infers state from transcript mtime — so **any** Claude Code process,
  even one started by hand, gets a button.
- **Focus** = PID→HWND (Windows) with a title-match fallback; macOS via AppleScript.
- **Build/test:** `cd deck && npm install && npm run build && npm test &&
  npm run selftest`. Deploy = copy `dev.claudefleet.streamDeckPlugin/` to
  `%APPDATA%\Elgato\StreamDeck\Plugins\` and restart Stream Deck. Publish via a
  GitHub Release asset. See `deck/README.md`.

---

## Port contract (permanent)

| Range | Purpose | Live use |
|---|---|---|
| 8000-8009 | Router ingress/admin | router **8001** (8000 = Portainer) |
| 8100-8199 | llama.cpp | 3090 **8101** |
| 8200-8299 | vLLM | 5090 **8201** |
| 8300-8399 | SGLang | (reserved) |
| 8400-8499 | Vision | Spark **8401** |
| 8500-8599 | Embeddings/rerankers | (reserved) |
| 9000-9099 | Metrics/exporters | Portainer API **9000**, Prometheus **9090** |

A runtime outside its contract must not enter the routing table.

---

## Stack IDs (Portainer, change on redeploy)

| name | endpoint | notes |
|---|---|---|
| `llm-router` | 3 | Go router (redeploy keeps the name; delete+recreate) |
| `qwen38-27b-3090` | 3 | 3090 MTP 262K |
| `qwen38-27b-dgxsparx` | 4 | Spark GB10 NVFP4 vLLM (v2) |
| `qwen38-flashnext-dgxsparx` | 4 | Spark Flash-Next vision |
| `qwen38-gpu-router` | 3 | legacy Python router (archived) |
