#!/usr/bin/env bash
# Diagnostic+fix probe: build vllm/mtp-patch:fix1 (drafter unquantized + probe),
# run MTP spec decode on a clean GPU, capture whether it loads or which mismatch
# remains (parameter.py probe_out.txt + docker logs).
set -uo pipefail
BASE=vllm/vllm-openai:vllm-arm64-cu13-0.25.1-7a33ba9
TIMG=vllm/mtp-patch:fix2
MODEL=/models/Qwen3.8-27B-Uncensored-NVFP4-ModelOpt
H=/home/darkmatter2222

docker rm -f qwen3.8-27b-dgxsparx mprobe ppatch sbench >/dev/null 2>&1
echo "=== build fix1 image (drafter unquantized + parameter.py probe) ==="
docker run --name ppatch --entrypoint bash -v $H/patcher_mtp_fix.py:/patcher_mtp_fix.py "$BASE" -c "python3 /patcher_mtp_fix.py"
docker commit ppatch "$TIMG" >/dev/null 2>&1 && echo "committed $TIMG"
docker rm -f ppatch >/dev/null 2>&1
echo "=== import sanity ==="
docker run --rm --entrypoint bash "$TIMG" -c "python3 -c 'import vllm.model_executor.parameter as m; import vllm.model_executor.models.qwen3_5_mtp as q; print(\"both import OK\")'" 2>&1 | tail -2

rm -f $H/probe_out.txt
echo "settling GPU (live + sbench stopped)..."; sleep 40
ARGS="--served-model-name qwen3.8 --host 0.0.0.0 --port 8006 --language-model-only --max-model-len 262144 --max-num-seqs 4 --max-num-batched-tokens 8192 --kv-cache-dtype fp8 --gpu-memory-utilization 0.85 --quantization modelopt_fp4 --attention-backend FLASHINFER --enable-chunked-prefill --async-scheduling --trust-remote-code --speculative-config '{\"method\":\"mtp\",\"num_speculative_tokens\":3}'"
docker run -d --name mprobe --gpus all --entrypoint /bin/bash -e CUDA_DEVICE_ORDER=PCI_BUS_ID -v /home/darkmatter2222/models:/models -v $H:/probeout "$TIMG" -lc "cd /models && vllm serve '$MODEL' $ARGS"
for i in $(seq 1 150); do
  st=$(docker inspect -f '{{.State.Status}}' mprobe 2>/dev/null)
  [ "$st" = "exited" ] && { echo "EXITED code=$(docker inspect -f '{{.State.ExitCode}}' mprobe)"; break; }
  curl -sk -o /dev/null -w '%{http_code}' http://localhost:8006/health 2>/dev/null | grep -q 200 && { echo "UP (spec decode)"; break; }
  sleep 5
done
echo "=== drafter/any mismatches captured (probe_out) ==="
sort -u $H/probe_out.txt 2>/dev/null | head -40
echo "(distinct: $(sort -u $H/probe_out.txt 2>/dev/null | wc -l))"
echo "=== health now ==="
curl -sk -o /dev/null -w '%{http_code}\n' http://localhost:8006/health 2>/dev/null
echo "=== crash/error tail ==="
docker logs mprobe 2>&1 | grep -E "AssertionError|NameError|AttributeError|RuntimeError|Engine core initialization|PROBE-MISMATCH|Speculative|speculat" | tail -25
