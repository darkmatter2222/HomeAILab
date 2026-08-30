# monitoring/ — Prometheus + Grafana fleet setup

Source-of-truth copies of the on-host monitoring config, kept in sync with the
live files on the DGX Spark. The live stack runs only on the **DGX Spark**
(`192.168.86.39`); this repo holds the editable mirror.

## Files

| file | live location | what it is |
|---|---|---|
| `prometheus.yml` | `/home/darkmatter2222/vllm-monitoring/prometheus.yml` (bind-mounted RO into the `prometheus` container, Portainer stack 12 / ep 4) | current scrape config. Update: `scp prometheus.yml dgxspark:/home/darkmatter2222/vllm-monitoring/prometheus.yml` then `curl -X POST http://192.168.86.39:9090/-/reload` |
| `adrsc9f-dashboard.restored.json` | Grafana (container `grafana`, `:3000`), dashboard **uid `adrsc9f`**, in the **Unified Storage `resource` table** of `vllm-monitoring_grafana-data/grafana.db` | **the deployed dashboard**: your v7 base + device filter + DCGM GPU row + fleet-uptime stat. This is what's live. |
| `adrsc9f-dashboard.pristine.json` | — | your last user-authored version (v7, "Real GPU Fixed + NVIDIA Refined Theme") pulled from `resource_history`, before any automated edit — restore source |
| `adrsc9f-dashboard.live.json` | — | an earlier classic-format export kept for diffing |

**How to update the dashboard:** edit `adrsc9f-dashboard.restored.json`, then
`scp` it to the Spark and run the small `resource`+`resource_history` update in
`deploy_restored.py` (see `monitoring/` — the v2 reader needs *both* rows synced),
then `docker restart grafana`. The dashboard is the **v2 resource envelope**
(`kind:Dashboard apiVersion:dashboard.grafana.app/v2`); `adrsc9f` uses the
**elements** layout format (`spec.elements` map + `spec.layout`).

## Grafana instance

- **Grafana 13.1.0**, container `grafana` on the Spark, port `3000` (LAN) and
  reverse-proxied as `http://192.168.86.48/grafana` (Databrick nginx).
- Creds: `admin` / (Grafana admin pass, in `.env` as `GRAFANA_ADMIN_PASSWORD`),
  or `agenticharness` / (Portainer pass, in `.env` as `PORTAINER_PASSWORD`).
- `GF_SERVER_SERVE_SUB_PATH=/grafana`. DB is **SQLite** on the
  `vllm-monitoring_grafana-data` docker volume.

### ⚠️ Unified Storage gotcha (Grafana 13)

Dashboards live in the **`resource`** table (`group=dashboard.grafana.app`,
`name=<uid>`), **not** the legacy `dashboard` table (which is empty). The API
read route `GET /api/dashboards/uid/<uid>` works, but the classic **write**
routes (`PUT/POST /api/dashboards/...`) 404 under Unified Storage in 13.1.
So dashboard edits are applied by updating the `resource` **and**
`resource_history` rows together (the history row is what reads are served
from; its `resource_version` must equal `resource.resource_version`).

## Dashboard `adrsc9f` — what's on it now (your v7 + additions)

Base is your **v7 "Real GPU Fixed + NVIDIA Refined Theme"** dashboard (all 41
panels intact — spec-decode acceptance by position, request rate/success/errors,
KV cache, prefix cache, output-TPS stat, etc.), with these **non-destructive**
additions layered on top:

- **`device`** query variable (source `label_values(up, device)`, regex
  `RTX|DGX Spark`, All→`.+`); `device=~"$device"` injected into every
  engine-level `vllm:*` / `http_*` query. **All** = fleet-wide; picking a
  device isolates one GPU.
- **GPU row** (4 DCGM panels): GPU util %, memory temp, power+temp, SM clock.
  These use the `dcgm` scrape job added to `prometheus.yml` (was running but
  never scraped before, so the "no-missing-gpu-metrics" tag finally holds).
- **Fleet uptime** stat: `up{job=~"vllm-dgxspark|vllm-5090|llamacpp-3090|qwen38-router"}`
  — the dead-5090-masking-stale-series problem is now visible at a glance.

Node/Disk/CPU panels stay Spark-only (the only host running node_exporter + DCGM).

## Prometheus scrape jobs (`prometheus.yml`)

| job | target | device | notes |
|---|---|---|---|
| `vllm-dgxspark` | host.docker.internal:8006 | DGX Spark | vLLM; 8006 is currently fronted by the `ds4` flashnext shim — vllm:* series appear when the vLLM stack serves 8006 |
| `vllm-5090` | 192.168.86.37:8006 | RTX 5090 | was mislabeled `llamacpp-5090`/runtime=llamacpp; it's vLLM (`vllm/vllm-openai`) |
| `llamacpp-3090` | 192.168.86.48:8006 | RTX 3090 | llama.cpp |
| `node` | host.docker.internal:9100 | DGX Spark | host CPU/mem/disk (Spark only) |
| `dcgm` | host.docker.internal:9400 | DGX Spark | GPU hardware (DCGM_FI_DEV_*); added — was running but never scraped |
| `qwen38-router` | 192.168.86.48:8010 | Router | FastAPI `/router/metrics` |
