#!/usr/bin/env bash
# One-off single-thread test: MTP on + max_num_seqs=1, clean GPU (live stack stopped).
# Matches the deployed YAML exactly (file-based JSON, MTP patcher first).
set -uo pipefail
IMG=vllm/vllm-openai:vllm-arm64-cu13-0.25.1-7a33ba9
MODEL=/models/Qwen3.8-27B-Uncensored-NVFP4-ModelOpt

docker rm -f s1test >/dev/null 2>&1
docker rm -f qwen3.8-27b-dgxsparx >/dev/null 2>&1   # stop live stack 49 to free the GPU
sleep 8
echo "GPU settling, launching s1test (MTP + max_num_seqs=1)..."

docker run -d --name s1test --gpus all --entrypoint /bin/bash \
  -p 8079:8006 -v /home/darkmatter2222/models:/models \
  "$IMG" -lc '
    set -uo pipefail
    python3 /models/Qwen3.8-27B-Uncensored-NVFP4-ModelOpt/.patch_mtp_fix.py
    echo "{\"enable_thinking\":false}" > /tmp/ctk.json
    echo "{\"method\":\"mtp\",\"num_speculative_tokens\":3}" > /tmp/spec.json
    vllm serve /models/Qwen3.8-27B-Uncensored-NVFP4-ModelOpt \
      --served-model-name qwen3.8 --host 0.0.0.0 --port 8006 --language-model-only \
      --max-model-len 262144 --max-num-seqs 1 --max-num-batched-tokens 8192 \
      --kv-cache-dtype fp8 --gpu-memory-utilization 0.85 \
      --quantization modelopt_fp4 --attention-backend FLASHINFER \
      --enable-chunked-prefill --async-scheduling --enable-prefix-caching --trust-remote-code \
      --default-chat-template-kwargs "$(cat /tmp/ctk.json)" \
      --reasoning-parser qwen3 --speculative-config "$(cat /tmp/spec.json)"
  '

# wait for health (MTP boot ~5 min incl FlashInfer autotune)
for i in $(seq 1 75); do
  if curl -sk http://127.0.0.1:8079/health 2>/dev/null | grep -q ok; then echo "UP after ${i} polls"; break; fi
  st=$(docker inspect -f "{{.State.Status}}" s1test 2>/dev/null)
  if [ "$st" = "exited" ]; then echo "CRASHED (status=$st)"; docker logs s1test 2>&1 | grep -iE 'error|assert|shape|mismatch|traceback|invalid' | tail -20; exit 1; fi
  sleep 6
done

echo "=== health ==="; curl -sk http://127.0.0.1:8079/health; echo
echo "=== MTP acceptance (from logs) ==="
docker logs s1test 2>&1 | grep -iE 'accept|draft|mtp' | tail -8
echo "=== 3x clean 200-tok decode-only (ignore_eos, MTP on, max_num_seqs=1) ==="
for r in 1 2 3; do
  python3 - <<'PY' 2>/dev/null
import json,time,urllib.request
url="http://127.0.0.1:8079/v1/completions"
d={"model":"qwen3.8","prompt":"Explain attention in transformers ","max_tokens":200,"temperature":0,"ignore_eos":True}
req=urllib.request.Request(url,data=json.dumps(d).encode(),headers={"Content-Type":"application/json"})
t=time.time();r=json.load(urllib.request.urlopen(req,timeout=120));w=time.time()-t
ct=r["usage"]["completion_tokens"];print(f"run{r}... generated={ct} wall={w:.2f}s -> {ct/w:.1f} tok/s (decode-only)")
PY
done
echo "=== leave s1test running; live stack still STOPPED (restore after) ==="
