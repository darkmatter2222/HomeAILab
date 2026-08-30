"""vLLM adapter (goal.md §5, §9, §20)."""

from __future__ import annotations

from typing import Any

from ..schemas import DeploymentConfig
from .base import EndpointMeta, EngineAdapter


class VllmAdapter(EngineAdapter):
    name = "vllm"

    def detect(self, meta: dict) -> float:
        score = 0.0
        hints = " ".join(meta.get("engine_hints", [])).lower()
        cmd = " ".join(meta.get("proc_cmdline", [])).lower()
        if "vllm" in hints or "vllm" in cmd:
            score += 0.7
        # vLLM-specific prometheus metric names are a strong signal.
        metrics = "\n".join(meta.get("metrics_lines", []))
        if "vllm:time_to_first_token_seconds" in metrics:
            score += 0.9
        if "vllm:num_requests_running" in metrics:
            score += 0.5
        ver = (meta.get("version") or "").lower()
        if ver:
            score += 0.1
        return min(score, 1.0)

    def normalize_config(
        self,
        raw_args: list[str],
        env: dict[str, str],
        meta: dict,
    ) -> DeploymentConfig:
        args = raw_args or list(meta.get("proc_cmdline", []))
        cfg = DeploymentConfig(engine=self.name, engine_image=meta.get("image"))
        cfg.all_args = args

        # Flag parsing: -key value pairs (vLLM uses --key value)
        kv: dict[str, str] = {}
        i = 0
        while i < len(args):
            a = args[i]
            if a.startswith("--"):
                key = a[2:]
                # value may be next arg, or after '='
                if "=" in a:
                    kv[key] = a.split("=", 1)[1]
                    i += 1
                elif i + 1 < len(args) and not args[i + 1].startswith("--"):
                    kv[key] = args[i + 1]
                    i += 2
                else:
                    kv[key] = "true"
                    i += 1
            else:
                i += 1

        def g(key: str) -> str | None:
            return kv.get(key)

        def fnum(key: str) -> float | None:
            v = g(key)
            if v is None:
                return None
            try:
                return float(v)
            except (ValueError, TypeError):
                return None

        def fint(key: str) -> int | None:
            v = g(key)
            if v is None:
                return None
            try:
                return int(v)
            except (ValueError, TypeError):
                return None

        cfg.model = g("model") or meta.get("model") or ""
        cfg.engine_version = meta.get("version")
        cfg.served_model_name = g("served-model-name")
        cfg.max_model_len = fint("max-model-len")
        cfg.dtype = g("dtype")
        cfg.quantization = g("quantization")
        cfg.kv_cache_dtype = g("kv-cache-dtype")
        cfg.gpu_memory_utilization = fnum("gpu-memory-utilization")
        cfg.max_num_seqs = fint("max-num-seqs")
        cfg.max_batched_tokens = fint("max-num-batched-tokens")
        cfg.tensor_parallel = fint("tensor-parallel-size")
        cfg.prefix_caching = (g("enable-prefix-caching") not in ("false", "False", "0")) if g("enable-prefix-caching") is not None else None
        cfg.enforce_eager = (g("enforce-eager") not in ("false", "False", "0")) if g("enforce-eager") is not None else None
        cfg.attention_backend = g("attention-backend") or g("attn-impl")
        cfg.tokenizer = g("tokenizer")
        cfg.async_scheduling = (g("async-scheduling") not in ("false", "False", "0")) if g("async-scheduling") is not None else None

        # Speculative decoding / MTP
        spec = g("speculative-config") or g("speculative-decoding-method") or g("spec-method")
        if spec:
            cfg.speculative_decoding = spec
        mtp = g("mtp-num-draft-tokens") or g("num-speculative-tokens") or g("speculative-draft-tokens")
        if mtp:
            cfg.mtp_config = f"num_draft={mtp}"
            if not cfg.speculative_decoding:
                cfg.speculative_decoding = "mtp"

        # Chunked prefill
        if g("enable-chunked-prefill") is not None:
            cfg.chunked_prefill = (g("enable-chunked-prefill") not in ("false", "False", "0"))

        # Compile options
        comp = g("compilation-config") or g("compilation-config")
        if comp:
            cfg.compile_options = comp

        # Scheduler
        sched = g("scheduler") or g("scheduling-policy")
        if sched:
            cfg.scheduler_config = sched

        # Environment (sensitive values redacted by caller's sanitizer)
        cfg.env_vars = {k: v for k, v in env.items() if k.upper().startswith(("VLLM", "CUDA", "HF", "MODEL", "NVIDIA", "PYTORCH"))}
        return cfg

    def metric_mapping(self) -> dict[str, str]:
        return {
            "ttft_s": "vllm:time_to_first_token_seconds",
            "itl_s": "vllm:inter_token_latency_seconds",
            "e2e_latency_s": "vllm:e2e_request_latency_seconds",
            "queue_time_s": "vllm:request_queue_time_seconds",
            "prefill_time_s": "vllm:request_prefill_time_seconds",
            "decode_time_s": "vllm:request_decode_time_seconds",
            "running_requests": "vllm:num_requests_running",
            "waiting_requests": "vllm:num_requests_waiting",
            "kv_cache_utilization": "vllm:gpu_cache_usage_per_engine",
            "prompt_tokens_total": "vllm:prompt_tokens_total",
            "generation_tokens_total": "vllm:generation_tokens_total",
            "requests_success": "vllm:num_requests_success",
            "requests_failed": "vllm:num_requests_failed",
            "prefix_cache_queries": "vllm:prefix_cache_queries",
            "prefix_cache_hits": "vllm:prefix_cache_hits",
        }

    def ignore_eos_supported(self) -> bool:
        return True

    def min_tokens_supported(self) -> bool:
        return True

    def extra_generation_params(self) -> dict[str, Any]:
        # vLLM additionally accepts these as top-level extras; the
        # streaming client already sends ignore_eos/min_tokens from
        # StreamConfig.  Nothing engine-specific to add for vLLM.
        return {}
