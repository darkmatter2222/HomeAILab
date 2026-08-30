"""llama.cpp / llama-server adapter (goal.md §5, §9, §20)."""

from __future__ import annotations

from typing import Any

from ..schemas import DeploymentConfig
from .base import EndpointMeta, EngineAdapter


class LlamaCppAdapter(EngineAdapter):
    name = "llamacpp"

    def detect(self, meta: dict) -> float:
        score = 0.0
        hints = " ".join(meta.get("engine_hints", [])).lower()
        cmd = " ".join(meta.get("proc_cmdline", [])).lower()
        if "llama" in hints or "llama-server" in cmd or "llama_cpp" in cmd:
            score += 0.7
        metrics = "\n".join(meta.get("metrics_lines", []))
        # llama-server exposes non-prefixed metrics in some builds.
        if "llama" in metrics.lower() or "llama_server" in metrics.lower():
            score += 0.4
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

        kv: dict[str, str] = {}
        i = 0
        while i < len(args):
            a = args[i]
            if a.startswith("-") and not a.startswith("--"):
                # llama.cpp mostly uses single-dash -key value
                key = a.lstrip("-")
                if i + 1 < len(args) and not args[i + 1].startswith("-"):
                    kv[key] = args[i + 1]
                    i += 2
                else:
                    kv[key] = "true"
                    i += 1
            else:
                i += 1

        def g(k: str) -> str | None:
            return kv.get(k)

        def fint(k: str) -> int | None:
            v = g(k)
            try:
                return int(v) if v is not None else None
            except (ValueError, TypeError):
                return None

        cfg.model = g("m") or g("hf-repo") or meta.get("model") or ""
        cfg.max_model_len = fint("c") or fint("ctx-size") or fint("context-size")
        cfg.max_num_seqs = fint("np") or fint("parallel")
        cfg.dtype = g("t")  # type hint (q4_0, q8_0) for KV; map to kv_cache_dtype
        if cfg.dtype:
            cfg.kv_cache_dtype = cfg.dtype
            cfg.dtype = None
        cfg.quantization = g("q") or g("ftype")
        cfg.tensor_parallel = fint("ngl") and 1  # GPU layers != TP; keep simple
        # Flash attention
        if g("fa") is not None:
            cfg.normalized["flash_attention"] = g("fa") not in ("0", "false", "False")
        # KV cache types
        if g("cache-type-k"):
            cfg.normalized["kv_cache_k_type"] = g("cache-type-k")
        if g("cache-type-v"):
            cfg.normalized["kv_cache_v_type"] = g("cache-type-v")
        # Speculative decoding
        if g("model-draft") or g("draft"):
            cfg.speculative_decoding = g("model-draft") or g("draft")
        if g("n-draft"):
            cfg.mtp_config = f"num_draft={g('n-draft')}"
        # mmap / mlock / threads
        if g("mmap") is not None:
            cfg.normalized["mmap"] = g("mmap") not in ("0", "false")
        if g("mlock") is not None:
            cfg.normalized["mlock"] = g("mlock") not in ("0", "false")
        if g("threads"):
            cfg.normalized["cpu_threads"] = g("threads")
        if g("batch"):
            cfg.normalized["batch_size"] = g("batch")
        if g("ubatch"):
            cfg.normalized["ubatch_size"] = g("ubatch")
        if g("n-gpu-layers") or g("ngl"):
            cfg.normalized["gpu_layers"] = g("n-gpu-layers") or g("ngl")
        # sampling
        if g("temp"):
            cfg.normalized["sampling_temperature"] = g("temp")
        if g("repeat-penalty"):
            cfg.normalized["sampling_repeat_penalty"] = g("repeat-penalty")

        cfg.env_vars = {k: v for k, v in env.items()
                        if k.upper().startswith(("GGML", "LLAMA", "CUDA", "MODEL"))}
        return cfg

    def metric_mapping(self) -> dict[str, str]:
        # llama-server exposes these as prometheus metrics (unprefixed or
        # with a llama_server_ prefix depending on build/version).
        return {
            "prompt_tokens_total": "llama_server_prompt_tokens_count",
            "prompt_processing_time_s": "llama_server_prompt_processing_seconds",
            "predict_tokens_total": "llama_server_predicted_tokens_count",
            "generation_time_s": "llama_server_generation_seconds",
            "processing_requests": "llama_server_requests_processing_count",
            "deferred_requests": "llama_server_requests_deferred_count",
            "context_hwm": "llama_server_context_high_water_mark",
        }

    def ignore_eos_supported(self) -> bool:
        return False
