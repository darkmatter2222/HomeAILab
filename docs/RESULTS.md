# Qwen3.8-27B on RTX 3090 — 262K Optimized Deployment

Deployed as Portainer stack `qwen38-27b-3090` on Databrick (192.168.86.48, endpoint 3),
YAML: `../qwen38-27b-3090-v1.yaml`. API on `:8006` (OpenAI + Anthropic-compatible).

## Why this config

Qwen3.8-27B is a **hybrid linear+full attention** model: 64 layers but only **16 are
full-attention** (the other 48 are linear/Mamba-like, near-O(1) per token). That makes the
KV cache for full 262K context tiny: **q4 KV ≈ 4.0 GiB, fp8 ≈ 8.0 GiB** (16 layers ×
GQA 4 kv-heads × 256 head-dim × 262144). So on a 24 GB 3090:

| piece | GiB |
|---|---|
| Qwen3.8-27B-Uncensored-Q4_K_M.gguf (fused, MTP head built in) | 16.8 |
| MTP draft head (built into the file) | ~0.3 |
| KV cache q4_0 @ 262144 | 4.0 |
| CUDA graph + activation overhead | ~2.5 |
| **total** | **~23.5 (fits 24 GB)** |

fp8 KV (8 GiB) OOMs — measured (crash). So **q4 KV** is the max-precision that fits.
The model is "abliterated" = refusal directions removed (Heretic LoRA merge); PPL 7.181,
near-f16 (7.156) because the imatrix was computed from f16.

Speed lever: **built-in MTP speculative decoding** (`--spec-type draft-mtp`) — no separate
1.9 GiB drafter file needed (that's why the fused file + MTP beats the DSpark drafter, which
can't fit 24 GB alongside the target).

## Tuning results (median of 5, 256-token generation, warm)

| config | decode tok/s | notes |
|---|---|---|
| no spec decode (baseline) | 40.6 | |
| MTP n_max=5 | 52.8 | |
| MTP n_max=4 | 56.8 | |
| **MTP n_max=3 (deployed)** | **~60** | **1.47x over baseline** |
| fp8 KV | crashed (OOM) | confirms q4 is the right KV dtype |

**n_max=3** is the optimum for the MTP head (accepted/step ≈ 2.0, acceptance ≈ 0.67).
Higher n_max costs more per verification step than it recovers.

## Final deployed numbers (stack #26, n_max=3)

- **Decode (steady-state): ~60 tok/s** (stable 58–60 across 5 runs).
- **Prefill: ~1150–1310 tok/s** (8K→97K; the linear-attention layers keep per-token cost
  low even at long contexts).
- **TTFT (short prompt, warm/cached): ~0.2 s.**
- **262K context: verified** — a 254290-token prompt fits (cap 262144); full prefill ≈ 515 s.
- GPU: 23590 MiB used of 24576 (driver 580.159), ~350 W / 1590 MHz (power-limited).

## Flags (final)

```
--model .../Qwen3.8-27B-Uncensored-Q4_K_M.gguf
--alias qwen3.8 --port 8006
--fit off --n-gpu-layers all --ctx-size 262144 --parallel 1
--cache-type-k q4_0 --cache-type-v q4_0
--spec-type draft-mtp --spec-draft-n-max 3
--batch-size 4096 --ubatch-size 512
--flash-attn on --cont-batching --load-mode mmap
--no-mmproj --jinja --reasoning auto --reasoning-format deepseek --reasoning-preserve
--metrics --perf
```

## How to re-tune

```
# decode spec tuning (GPU must be free — stop the stack container first)
bash qwen3.8-27b/tune.sh nmax      # n_max sweep (median5)
bash qwen3.8-27b/tune.sh nospec    # no-spec baseline + fp8 KV
bash qwen3.8-27b/prefilltest.sh    # prefill t/s at 32K/128K/256K chars
# full suite against a running server:
python3 qwen3.8-27b/bench.py http://<host>:8006
```

Deploy a new config: edit `../qwen38-27b-3090-v1.yaml` env knobs (SPEC_N_MAX, KV_K/V,
BATCH_SIZE, UBATCHE_SIZE, TOTAL_CONTEXT), then `bash qwen3.8-27b/redeploy.sh`
(deletes + recreates the Portainer stack on endpoint 3).

## Downloads (25 MiB/s cap)

The model + chat template already live on the Databrick, so steady-state restarts download
nothing. First-run downloads use `curl --limit-rate` (25 MiB/s) for the target GGUF. The
fused Q4_K_M is self-contained (MTP head inline) so no second file is fetched.
