#!/usr/bin/env python3
"""
Standard benchmark suite for the 3090 Qwen3.8-27B deployment.
Measures the metrics that matter for an inference deployment:
  - TTFT        : time to first token (s)
  - prefill     : prompt tokens/s
  - decode      : completion tokens/s (generation throughput)
  - e2e         : total wall time for a full request (s)
  - 262K        : max-context verification (a real 262144-token prompt)

Runs against the OpenAI-compatible API on :8006.
Usage:  python3 bench.py [base_url]
"""
import json, time, urllib.request, sys, os, random

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8006"
MODEL = os.environ.get("BENCH_MODEL", "qwen3.8")
MAXCTX = 262144

def post(path, payload, timeout=1800):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read().decode()
    t1 = time.perf_counter()
    return json.loads(body), (t1 - t0)

def est_tokens(text):
    # rough: ~4 chars/token for the tokenizer; good enough for planning
    return max(1, len(text) // 4)

def one(prompt, max_tokens, temp=0, timeout=1800):
    payload = {
        "model": MODEL,
        "prompt": prompt,
        "max_tokens": max_tokens,
        "temperature": temp,
        "stream": False,
    }
    t_start = time.perf_counter()
    data, elapsed = post("/v1/completions", payload, timeout)
    usage = data.get("usage", {})
    pt = usage.get("prompt_tokens", 0)
    ct = usage.get("completion_tokens", 0)
    # TTFT: without streaming we can't get a true first-token time, so we
    # approximate TTFT with a tiny streaming call separately; here we report
    # prefill/decode from the completion.
    prefill_tps = pt / max(elapsed, 1e-6) if ct == 0 else None  # prefill-only proxy
    decode_tps = ct / max(elapsed, 1e-6)
    timings = data.get("choices", [{}])[0].get("timings", {}) if data.get("choices") else {}
    return {
        "prompt_tokens": pt,
        "completion_tokens": ct,
        "wall_s": round(elapsed, 3),
        "decode_tps": round(decode_tps, 2),
        "total_tps": round((pt + ct) / max(elapsed, 1e-6), 2),
        "server_timings": timings,
    }

def ttft_stream(prompt, max_tokens=32):
    """True TTFT via streaming: time until the first content chunk."""
    payload = {
        "model": MODEL,
        "prompt": prompt,
        "max_tokens": max_tokens,
        "temperature": 0,
        "stream": True,
    }
    req = urllib.request.Request(
        BASE + "/v1/completions",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    t0 = time.perf_counter()
    t_first = None
    n_chunks = 0
    t_end = t0
    with urllib.request.urlopen(req, timeout=1800) as r:
        for raw in r:
            line = raw.decode().strip()
            if not line or not line.startswith("data:"):
                continue
            d = line[5:].strip()
            if d == "[DONE]":
                break
            try:
                obj = json.loads(d)
            except Exception:
                continue
            t_end = time.perf_counter()
            chunk = obj.get("choices", [{}])[0].get("text", "")
            if chunk:
                if t_first is None:
                    t_first = time.perf_counter() - t0
                n_chunks += len(chunk)
    # decode throughput from the stream
    decode_tps = (n_chunks / (t_end - t_first)) if (t_first is not None and t_end > t_first) else 0.0
    return {"ttft_s": round(t_first, 3) if t_first else None,
            "decode_tps": round(decode_tps, 2),
            "chars": n_chunks}

def run_suite():
    print("=== Qwen3.8-27B 3090 Standard Benchmark ===")
    print("base:", BASE, " model:", MODEL, " maxctx:", MAXCTX)
    results = {}

    # 1. Prefill speed at increasing prompt sizes (short generation so prefill dominates)
    print("\n-- prefill (prompt tok/s, 16-token generation) --")
    for label, nchars in [("8K-ish", 32_000), ("32K-ish", 128_000), ("64K-ish", 256_000)]:
        prompt = ("The system prompt contains a long document. " * (nchars // 40))[:nchars]
        try:
            r = one(prompt, 16)
            results[f"prefill_{label}"] = r
            print(f"  {label}: prompt~{r['prompt_tokens']}tok prefill~{r['total_tps']} t/s (all-in) wall={r['wall_s']}s")
        except Exception as e:
            print(f"  {label}: ERROR {e}")

    # 2. TTFT + decode on a representative chat-style prompt
    print("\n-- TTFT + decode (stream, representative) --")
    for label, prompt in [
        ("short", "Explain speculative decoding in one paragraph."),
        ("medium", "Summarize this: " + ("deep learning improves with scale " * 200)),
    ]:
        try:
            r = ttft_stream(prompt, 64)
            results[f"ttft_{label}"] = r
            print(f"  {label}: TTFT={r['ttft_s']}s decode={r['decode_tps']} tok/s")
        except Exception as e:
            print(f"  {label}: ERROR {e}")

    # 3. Full 262K context verification
    print("\n-- 262K max-context verification --")
    # Qwen tokenizer ~3.2 chars/token here. Target ~258K tokens (leave room for
    # the 8 generated within the 262144 cap).
    target_tokens = 258_000
    # measured ~2.5 chars/token for this filler (number-prefixed words tokenize
    # efficiently); 2.5 * 258K ~= 645K chars -> ~258K tokens, under the cap.
    target_chars = int(target_tokens * 2.5)
    buf = []
    cur = 0
    i = 0
    pool = ["consequently", "furthermore", "therefore", "meanwhile", "likewise",
            "whereas", "henceforth", "notwithstanding", "moreover", "thereupon"]
    while cur < target_chars:
        s = f"t{i} {pool[i % len(pool)]} "
        buf.append(s); cur += len(s); i += 1
    big = "".join(buf)
    try:
        r = one(big, 8, timeout=2400)
        results["maxctx_262k"] = r
        ok = r["prompt_tokens"] >= 255_000
        print(f"  262K: prompt_tokens={r['prompt_tokens']} (target>255K: {ok}) prefill+decode wall={r['wall_s']}s")
    except Exception as e:
        results["maxctx_262k"] = {"error": str(e)}
        print(f"  262K: ERROR {e}")

    # 4b. spec-decode acceptance snapshot from /metrics
    try:
        mt = json.load(urllib.request.urlopen(BASE + "/metrics", timeout=30))
        def g(name):
            for l in mt:
                if l.startswith(name + " "):
                    return float(l.split()[-1])
            return None
        drafts = g("llamacpp:spec_decode_num_draft_tokens_total")
        acc = g("llamacpp:spec_decode_num_accepted_tokens_total")
        steps = g("llamacpp:spec_decode_num_drafts_total")
        results["spec_decode"] = {
            "draft_tokens": drafts, "accepted_tokens": acc, "verify_steps": steps,
            "acceptance_rate": round(acc / drafts, 3) if drafts else None,
            "accepted_per_step": round(acc / steps, 3) if steps else None,
        }
        print("\n-- spec decode (from /metrics, cumulative) --")
        print(" ", results["spec_decode"])
    except Exception as e:
        print("spec_decode metrics: ERROR", e)

    # 4. Long-form decode (512 tokens) for steady-state decode throughput
    print("\n-- steady-state decode (512 tokens) --")
    try:
        r = one("Write a detailed technical overview of flash attention.", 512)
        results["decode_512"] = r
        print(f"  decode: {r['completion_tokens']}tok wall={r['wall_s']}s decode={r['decode_tps']} tok/s total={r['total_tps']} t/s")
    except Exception as e:
        print(f"  decode512: ERROR {e}")

    print("\n=== SUMMARY ===")
    print(json.dumps(results, indent=2))
    return results

if __name__ == "__main__":
    run_suite()
