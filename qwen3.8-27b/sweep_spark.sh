#!/usr/bin/env bash
# Concurrency sweep on the DGX Spark (GB10) for Qwen3.8-27B-Uncensored-Q4_K_M.
# Measures, per --parallel value: per-stream decode tok/s, aggregate tok/s,
# and TTFT.  Median of N runs.  Run on the Spark host (model mounted at /m).
set -uo pipefail
IMG=ghcr.io/ggml-org/llama.cpp:server-cuda
MODEL=/m/Qwen3.8-27B-Uncensored-GGUF/Qwen3.8-27B-Uncensored-Q4_K_M.gguf
TMPL=/m/Qwen3.8-27B-Uncensored-GGUF/qwen-fixed-chat-template-v22.jinja
PORT=8077
CTX=262144
CTX_CAP="${CTX_CAP:-262144}"   # override for the 262K-context check
NPAR="${1:-1 2 3 4}"
N_RUN="${2:-3}"

start() {  # $1 = parallel
  local p="$1"; shift
  docker rm -f sweep_srv >/dev/null 2>&1
  docker run -d --name sweep_srv --gpus all --entrypoint /bin/bash \
    -e CUDA_DEVICE_ORDER=PCI_BUS_ID -p "$PORT:8006" \
    -v /home/darkmatter2222/models:/m "$IMG" \
    -lc "/app/llama-server \
      --model '$MODEL' --alias qwen3.8 --host 0.0.0.0 --port 8006 \
      --fit off --n-gpu-layers all --ctx-size $CTX_CAP --parallel '$p' \
      --cache-type-k q4_0 --cache-type-v q4_0 \
      --flash-attn on --cont-batching --load-mode mmap \
      --batch-size 8192 --ubatch-size 1024 \
      --no-mmproj --jinja --reasoning auto --reasoning-format deepseek --reasoning-preserve \
      --spec-type draft-mtp --spec-draft-n-max 3 \
      --chat-template-file '$TMPL' --log-verbosity 1
      2>&1" >/dev/null 2>&1
  # health or crash
  local ok=0
  for i in $(seq 1 120); do
    curl -sk http://127.0.0.1:$PORT/health 2>/dev/null | grep -q ok && { ok=1; break; }
    docker inspect -f '{{.State.Status}}' sweep_srv 2>/dev/null | grep -q exited && { echo "  [p=$p] CRASHED"; docker logs sweep_srv 2>&1 | grep -iE 'error|fatal|no such|oom' | head; return 1; }
    sleep 2
  done
  [ "$ok" = "1" ] || { echo "  [p=$p] TIMEOUT"; docker logs sweep_srv 2>&1 | grep -iE 'error|fatal' | head; return 1; }
}

stop() { docker rm -f sweep_srv >/dev/null 2>&1; }

# one run: launch p concurrent 256-token gens, measure wall time + per-stream tps
one_run() {
  local p="$1"
  local pids=() t0
  t0=$(date +%s.%N)
  for i in $(seq 1 "$p"); do
    ( curl -sk http://127.0.0.1:$PORT/v1/completions -H 'Content-Type: application/json' \
        -d '{"model":"qwen3.8","prompt":"Explain transformers. ","max_tokens":256,"temperature":0,"stream":false}' \
        >/dev/null 2>&1 ) &
    pids+=("$!")
  done
  wait "${pids[@]}" 2>/dev/null
  local t1 elapsed
  t1=$(date +%s.%N); elapsed=$(python3 -c "print($t1-$t0)")
  python3 -c "print(round(($p*256)/$elapsed,1))"   # aggregate tok/s
}

for p in $NPAR; do
  echo "==================================================================="
  echo " parallel=$p   (ctx cap=$CTX_CAP)"
  if ! start "$p"; then stop; continue; fi
  # warmup (light, 1 stream)
  curl -sk http://127.0.0.1:$PORT/v1/completions -H 'Content-Type: application/json' \
    -d '{"model":"qwen3.8","prompt":"warmup","max_tokens":128,"temperature":0}' >/dev/null 2>&1
  agg="" ttfts=""
  for r in $(seq 1 "$N_RUN"); do
    a=$(one_run "$p")
    agg="$agg $a"
  done
  # TTFT: one stream, measure time to first byte
  local ttf
  ttf=$(python3 - "$p" <<'PY'
import urllib.request,json,sys,time
p=int(sys.argv[1])
t0=time.time()
req=urllib.request.Request("http://127.0.0.1:8077/v1/completions",
    data=json.dumps({"model":"qwen3.8","prompt":"Hi","max_tokens":64,"stream":True,"temperature":0}).encode(),
    headers={"Content-Type":"application/json"})
with urllib.request.urlopen(req,timeout=60) as r:
    for _ in r:  # first chunk
        break
print(round(time.time()-t0,3))
PY
)
  agg_med=$(echo $agg | tr ' ' '\n' | sort -n | sed -n "$(( (N_RUN+1)/2 ))p")
  echo "  parallel=$p  agg_decode(median$N_RUN)=${agg_med} tok/s   runs:$agg   ttft=${ttf}s"
  stop
done
echo "done"
