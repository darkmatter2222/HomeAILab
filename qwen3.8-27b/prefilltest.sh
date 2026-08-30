#!/usr/bin/env bash
# Prefill throughput at several prompt sizes for a given flag set.
set -uo pipefail
IMG=ghcr.io/ggml-org/llama.cpp:server-cuda12
MODEL=/m/Qwen3.8-27B-Uncensored-GGUF/Qwen3.8-27B-Uncensored-Q4_K_M.gguf
TMPL=/m/Qwen3.8-27B-Uncensored-GGUF/qwen-fixed-chat-template-v22.jinja
PORT=8077
CFG=(--flash-attn on --cont-batching --load-mode mmap --spec-type draft-mtp --spec-draft-n-max 3 --batch-size 4096 --ubatch-size 512)
docker run -d --name pf_srv --gpus all -p $PORT:8006 -v /home/darkmatter2222/models:/m \
  -e CUDA_DEVICE_ORDER=PCI_BUS_ID $IMG \
  --model "$MODEL" --alias qwen3.8 --host 0.0.0.0 --port 8006 \
  --fit off --n-gpu-layers all --ctx-size 262144 --parallel 1 \
  --cache-type-k q4_0 --cache-type-v q4_0 --no-mmproj --jinja \
  --reasoning auto --reasoning-format deepseek --reasoning-preserve --log-verbosity 1 \
  --chat-template-file "$TMPL" "${CFG[@]}" 2>/dev/null
for i in $(seq 1 90); do
  curl -sk http://127.0.0.1:$PORT/health 2>/dev/null | grep -q ok && break
  sleep 2
done
curl -sk http://127.0.0.1:$PORT/v1/completions -H 'Content-Type: application/json' -d '{"model":"qwen3.8","prompt":"warm","max_tokens":4}' >/dev/null 2>&1
echo "### prefill throughput (prompt_tokens / prefill_wall) at winning config"
for nchars in 32000 128000 256000; do
  python3 -c "
import json,urllib.request,time,random
random.seed(7)
pool=['consequently','furthermore','therefore','meanwhile','likewise','whereas','henceforth','notwithstanding','moreover','thereupon']
buf=[];cur=0;i=0;nc=$nchars
while cur<nc:
    s=f't{i} {pool[i%len(pool)]} ';buf.append(s);cur+=len(s);i+=1
big=''.join(buf)
payload={'model':'qwen3.8','prompt':big,'max_tokens':4,'temperature':0}
req=urllib.request.Request('http://127.0.0.1:$PORT/v1/completions',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
t0=time.perf_counter()
d=json.load(urllib.request.urlopen(req,timeout=2400))
t1=time.perf_counter()
pt=d['usage']['prompt_tokens']
print(f'  chars~{nc}: prompt_tokens={pt}  prefill+decode_wall={t1-t0:.1f}s  prefill_tps~{pt/(t1-t0):.0f}')
"
done
docker rm -f pf_srv >/dev/null 2>&1
