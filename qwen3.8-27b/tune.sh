#!/usr/bin/env bash
# Robust decode tuning: model mounted at /m. Longer warmup, median of runs.
set -uo pipefail
IMG=ghcr.io/ggml-org/llama.cpp:server-cuda12
MODEL=/m/Qwen3.8-27B-Uncensored-GGUF/Qwen3.8-27B-Uncensored-Q4_K_M.gguf
TMPL=/m/Qwen3.8-27B-Uncensored-GGUF/qwen-fixed-chat-template-v22.jinja
PORT=8077
measure() {
  local label="$1"; shift
  docker run -d --name tune_srv --gpus all -p $PORT:8006 -v /home/darkmatter2222/models:/m \
    -e CUDA_DEVICE_ORDER=PCI_BUS_ID $IMG \
    --model "$MODEL" --alias qwen3.8 --host 0.0.0.0 --port 8006 \
    --fit off --n-gpu-layers all --ctx-size 262144 --parallel 1 \
    --cache-type-k q4_0 --cache-type-v q4_0 --no-mmproj --jinja \
    --reasoning auto --reasoning-format deepseek --reasoning-preserve --log-verbosity 1 \
    --chat-template-file "$TMPL" "$@" 2>/dev/null
  local ok=0
  for i in $(seq 1 90); do
    curl -sk http://127.0.0.1:$PORT/health 2>/dev/null | grep -q ok && { ok=1; break; }
    docker inspect -f '{{.State.Status}}' tune_srv 2>/dev/null | grep -q exited && { echo "[$label] CRASHED"; docker logs tune_srv 2>&1 | grep -iE 'error|fatal|no such' | head; docker rm -f tune_srv >/dev/null 2>&1; return; }
    sleep 2
  done
  [ "$ok" = "1" ] || { echo "[$label] TIMEOUT"; docker rm -f tune_srv >/dev/null 2>&1; return; }
  # warm: 3x256
  for w in 1 2 3; do
    curl -sk http://127.0.0.1:$PORT/v1/completions -H 'Content-Type: application/json' -d '{"model":"qwen3.8","prompt":"warmup text","max_tokens":256,"temperature":0}' >/dev/null 2>&1
  done
  # 5 measurement runs, report median
  local vals=""
  for r in 1 2 3 4 5; do
    t0=$(date +%s.%N)
    curl -sk http://127.0.0.1:$PORT/v1/completions -H 'Content-Type: application/json' \
      -d '{"model":"qwen3.8","prompt":"Explain how a transformer attention head works.","max_tokens":256,"temperature":0}' >/dev/null 2>&1
    t1=$(date +%s.%N)
    vals="$vals $(python3 -c "print(round(256/($t1-$t0),1))")"
  done
  local med=$(echo $vals | tr ' ' '\n' | sort -n | sed -n '3p')
  echo "### [$label] decode(median5)=${med} tok/s   runs:$vals"
  docker rm -f tune_srv >/dev/null 2>&1
}
COMMON=(--flash-attn on --cont-batching --load-mode mmap)
if [ "${1:-}" = "nmax" ]; then
  for n in 3 4 5; do measure "nmax=$n" "${COMMON[@]}" --spec-type draft-mtp --spec-draft-n-max $n --batch-size 4096 --ubatch-size 512; done
elif [ "${1:-}" = "batch" ]; then
  for bu in "4096 512" "8192 1024" "16384 1024" "8192 512"; do set -- $bu; measure "b=$1,u=$2" "${COMMON[@]}" --spec-type draft-mtp --spec-draft-n-max 4 --batch-size $1 --ubatch-size $2; done
elif [ "${1:-}" = "nospec" ]; then
  measure "no-spec(baseline)" "${COMMON[@]}" --batch-size 4096 --ubatch-size 512
  measure "kv=fp8,batch=8192" "${COMMON[@]}" --spec-type draft-mtp --spec-draft-n-max 4 --batch-size 8192 --ubatch-size 1024 --cache-type-k f8_e5m2 --cache-type-v f8_e5m2
fi
