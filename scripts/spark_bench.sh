#!/usr/bin/env bash
# Single-stream decode-speed A/B on the Spark. Run each variant, report tok/s.
# Usage: spark_bench.sh <label> <maxseqs> <prefcache on/off> <spec off/on> [extra flags]
set -uo pipefail
IMG=vllm/vllm-openai:vllm-arm64-cu13-0.25.1-7a33ba9
MODEL=/models/Qwen3.8-27B-Uncensored-NVFP4-ModelOpt
PORT=8079
VARIANT="${1:-base}"
MAXSEQS="${2:-16}"
PREFCACHE="${3:-on}"
SPEC="${4:-off}"
EXTRA="${5:-}"

# Stop the live deploy (holds the GPU + 79 GiB fp8 KV) so the bench container fits.
docker rm -f qwen3.8-27b-dgxsparx >/dev/null 2>&1
docker rm -f sbench >/dev/null 2>&1
sleep 8

ARGS="--served-model-name qwen3.8 --host 0.0.0.0 --port 8006 --language-model-only \
  --max-model-len 262144 --max-num-seqs ${MAXSEQS} --max-num-batched-tokens 8192 \
  --kv-cache-dtype fp8 --gpu-memory-utilization 0.85 --quantization modelopt_fp4 \
  --attention-backend FLASHINFER --enable-chunked-prefill --async-scheduling --trust-remote-code"
[ "$PREFCACHE" = "on" ] && ARGS="$ARGS --enable-prefix-caching"
[ -n "$EXTRA" ] && ARGS="$ARGS $EXTRA"
[ "$SPEC" = "on" ] && ARGS="$ARGS --speculative-config '{\"method\":\"mtp\",\"num_speculative_tokens\":3}'"

echo "=== $VARIANT  maxseqs=$MAXSEQS prefcache=$PREFCACHE spec=$SPEC ==="
docker run -d --name sbench --gpus all --entrypoint /bin/bash \
  -e CUDA_DEVICE_ORDER=PCI_BUS_ID -p "$PORT:8006" \
  -v /home/darkmatter2222/models:/models "$IMG" \
  -lc "cd /models && vllm serve '$MODEL' $ARGS" >/dev/null 2>&1
ok=0
for i in $(seq 1 120); do
  curl -sk "http://127.0.0.1:$PORT/health" 2>/dev/null | grep -q ok && { ok=1; break; }
  docker inspect -f 'STATUS={{.State.Status}}' sbench 2>/dev/null | grep -q 'exited' && { echo "CRASH:"; docker logs sbench 2>&1 | grep -iE 'Error|ValueError|no memory|assert|unrecogn' | tail -6; break; }
  sleep 3
done
[ "$ok" = "1" ] || { echo "  (did not come up)"; docker rm -f sbench >/dev/null 2>&1; exit 0; }
curl -sk "http://127.0.0.1:$PORT/v1/completions" -H 'Content-Type: application/json' \
  -d '{"model":"qwen3.8","prompt":"warm","max_tokens":64,"temperature":0}' >/dev/null 2>&1
python3 - "$PORT" <<'PY'
import urllib.request,json,time,sys
port=sys.argv[1]
PROMPT="Explain the transformer attention mechanism in detail. "
def one(n):
    req=urllib.request.Request(f'http://127.0.0.1:{port}/v1/completions',
      data=json.dumps({'model':'qwen3.8','prompt':PROMPT,'max_tokens':n,'temperature':0}).encode(),
      headers={'Content-Type':'application/json'})
    t0=time.time()
    with urllib.request.urlopen(req,timeout=180) as r: json.load(r)
    return (time.time()-t0)
n=256
times=[one(n) for _ in range(2)]
med=sorted(times)[len(times)//2]
print(f"  single-stream {n} tok: {n/med:.1f} tok/s  (runs {['%.1f'%t for t in times]}s)")
PY
docker rm -f sbench >/dev/null 2>&1
echo "done-$VARIANT"
