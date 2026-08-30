#!/usr/bin/env bash
# Concurrency sweet-spot sweep for the NVFP4 vLLM build on the DGX Spark.
# For each --max-num-seqs value: start a vLLM server (NVFP4, 262K, fp8 KV),
# warm, then 3 steady-state runs of N-concurrent 256-tok gens; report
# aggregate tok/s + TTFT.  Run on the Spark host.
set -uo pipefail
IMG=vllm/vllm-openai:vllm-arm64-cu13-0.25.1-7a33ba9
MODEL=/models/Qwen3.8-27B-Uncensored-NVFP4-ModelOpt
PORT=8077
PARGS="${1:-2 4 8 12 16}"

start() {
  local n="$1"
  # JSON flag written to a file to keep its quotes intact (shell strips them inline).
  echo '{"enable_thinking":false}' > /tmp/ctk.json
  docker rm -f vvllm >/dev/null 2>&1
  docker run -d --name vvllm --gpus all --entrypoint /bin/bash \
    -e CUDA_DEVICE_ORDER=PCI_BUS_ID -p "$PORT:8006" \
    -v /home/darkmatter2222/models:/models "$IMG" \
    -lc "CTK=\$(cat /models/.ctk.json 2>/dev/null || echo '{\"enable_thinking\":false}'); \
      vllm serve $MODEL --served-model-name qwen3.8 --host 0.0.0.0 --port 8006 \
      --language-model-only --max-model-len 262144 --max-num-seqs '$n' \
      --max-num-batched-tokens 8192 --kv-cache-dtype fp8 \
      --gpu-memory-utilization 0.85 --quantization modelopt_fp4 \
      --attention-backend FLASHINFER --enable-chunked-prefill --async-scheduling \
      --enable-prefix-caching --trust-remote-code \
      --default-chat-template-kwargs \"\$CTK\" \
      --reasoning-parser qwen3 --enable-auto-tool-choice --tool-call-parser qwen3_coder" >/dev/null 2>&1
  local ok=0
  for i in $(seq 1 90); do
    curl -sk "http://127.0.0.1:$PORT/health" 2>/dev/null | grep -q ok && { ok=1; break; }
    docker inspect -f 'STATUS={{.State.Status}}' vvllm 2>/dev/null | grep -q 'STATUS=exited' && { echo "  n=$n CRASH"; docker logs vvllm 2>&1 | grep -iE 'ValueError|RuntimeError|no memory' | head; break; }
    sleep 3
  done
  [ "$ok" = "1" ] || return 1
}

agg() {  # $1 = concurrency
  local n="$1" t0 t1
  t0=$(date +%s.%N)
  for i in $(seq 1 "$n"); do
    ( curl -sk "http://127.0.0.1:$PORT/v1/completions" -H 'Content-Type: application/json' \
        -d '{"model":"qwen3.8","prompt":"Explain attention. ","max_tokens":256,"temperature":0}' >/dev/null 2>&1 ) &
  done
  wait
  t1=$(date +%s.%N)
  python3 -c "print(round($n*256/($t1-$t0),1))"
}

for n in $PARGS; do
  echo "=== max_num_seqs=$n ==="
  if ! start "$n"; then docker rm -f vvllm >/dev/null 2>&1; continue; fi
  # warm 2 streams
  for w in 1 2; do
    curl -sk "http://127.0.0.1:$PORT/v1/completions" -H 'Content-Type: application/json' \
      -d '{"model":"qwen3.8","prompt":"warm","max_tokens":128,"temperature":0}' >/dev/null 2>&1
  done
  vals=""
  for r in 1 2 3; do
    a=$(agg "$n"); vals="$vals $a"
  done
  med=$(echo $vals | tr ' ' '\n' | sort -n | sed -n '2p')
  # TTFT (one stream)
  ttf=$(python3 - "$n" <<'PY'
import urllib.request,json,sys,time
n=int(sys.argv[1])
t0=time.time()
req=urllib.request.Request("http://127.0.0.1:8077/v1/completions",
  data=json.dumps({"model":"qwen3.8","prompt":"Hi","max_tokens":32,"stream":True,"temperature":0}).encode(),
  headers={"Content-Type":"application/json"})
with urllib.request.urlopen(req,timeout=60) as r:
    for _ in r: break
print(round(time.time()-t0,3))
PY
)
  echo "  n=$n  agg(median3)=${med} tok/s   runs:$vals   ttft=${ttf}s"
  docker rm -f vvllm >/dev/null 2>&1
done
echo done-vllm-sweep
