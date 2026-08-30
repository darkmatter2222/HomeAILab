#!/usr/bin/env bash
# Clean steady-state high-concurrency sweep on the DGX Spark.
# For each parallel value: start server (ctx 262144, q4 KV, MTP n_max=3),
# warm 1 stream, then 3 steady-state runs of p-concurrent 512-token gens;
# report aggregate median tok/s.
set -uo pipefail
IMG=ghcr.io/ggml-org/llama.cpp:server-cuda
MODEL=/m/Qwen3.8-27B-Uncensored-GGUF/Qwen3.8-27B-Uncensored-Q4_K_M.gguf
TMPL=/m/Qwen3.8-27B-Uncensored-GGUF/qwen-fixed-chat-template-v22.jinja
PORT=8077
PARGS="${1:-4 6 8 12 16}"

for p in $PARGS; do
  docker rm -f ssrv >/dev/null 2>&1
  docker run -d --name ssrv --gpus all --entrypoint /bin/bash \
    -e CUDA_DEVICE_ORDER=PCI_BUS_ID -p "$PORT:8006" \
    -v /home/darkmatter2222/models:/m "$IMG" \
    -lc "/app/llama-server \
      --model '$MODEL' --alias qwen3.8 --host 0.0.0.0 --port 8006 \
      --fit off --n-gpu-layers all --ctx-size 262144 --parallel '$p' \
      --cache-type-k q4_0 --cache-type-v q4_0 \
      --flash-attn on --cont-batching --load-mode mmap \
      --batch-size 8192 --ubatch-size 1024 \
      --no-mmproj --jinja --reasoning auto --reasoning-format deepseek --reasoning-preserve \
      --spec-type draft-mtp --spec-draft-n-max 3 \
      --chat-template-file '$TMPL' --log-verbosity 1" >/dev/null 2>&1
  ok=0
  for i in $(seq 1 120); do
    curl -sk "http://127.0.0.1:$PORT/health" 2>/dev/null | grep -q ok && { ok=1; break; }
    docker inspect -f 'STATUS={{.State.Status}}' ssrv 2>/dev/null | grep -q 'STATUS=exited' && { echo "  p=$p CRASH"; docker logs ssrv 2>&1 | grep -iE 'error|fatal|oom' | head; break; }
    sleep 2
  done
  if [ "$ok" != "1" ]; then docker rm -f ssrv >/dev/null 2>&1; continue; fi

  # warm: one 512-tok gen
  curl -sk "http://127.0.0.1:$PORT/v1/completions" -H 'Content-Type: application/json' \
    -d '{"model":"qwen3.8","prompt":"warm","max_tokens":512,"temperature":0}' >/dev/null 2>&1

  vals=""
  for r in 1 2 3; do
    t0=$(date +%s.%N)
    for i in $(seq 1 "$p"); do
      ( curl -sk "http://127.0.0.1:$PORT/v1/completions" -H 'Content-Type: application/json' \
          -d '{"model":"qwen3.8","prompt":"Explain attention. ","max_tokens":512,"temperature":0}' >/dev/null 2>&1 ) &
    done
    wait
    t1=$(date +%s.%N)
    vals="$vals $(python3 -c "print(round($p*512/($t1-$t0),1))")"
  done
  med=$(echo $vals | tr ' ' '\n' | sort -n | sed -n '2p')
  echo "parallel=$p  agg(median3)=${med} tok/s   runs:$vals"
  docker rm -f ssrv >/dev/null 2>&1
done
echo done-clean
