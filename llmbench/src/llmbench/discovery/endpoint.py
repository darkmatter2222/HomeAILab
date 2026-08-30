"""Target endpoint discovery + engine auto-detection (goal.md §5, §7, §9).

Discovers model, max context, engine, version, image, startup args, and
/metrics availability from a live OpenAI-compatible endpoint.
"""

from __future__ import annotations

import asyncio
from typing import Optional

import httpx

from ..adapters.base import EndpointMeta, EngineAdapter
from ..adapters.generic import GenericAdapter
from ..adapters.llamacpp import LlamaCppAdapter
from ..adapters.vllm import VllmAdapter
from ..security.sanitize import Sanitizer

# Registered adapters in priority order.  Add new engines here.
ADAPTERS: list[type[EngineAdapter]] = [
    VllmAdapter,
    LlamaCppAdapter,
]


def get_adapter(engine_name: str) -> EngineAdapter:
    table = {a.name: a for a in ADAPTERS}
    if engine_name in table:
        return table[engine_name]()
    return GenericAdapter()


class EndpointProbe:
    """Discovers endpoint metadata via OpenAI API + /metrics + /version."""

    def __init__(
        self,
        base_url: str,
        model: str = "auto",
        api_key: Optional[str] = None,
        metrics_url: Optional[str] = None,
        timeout: float = 30.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.metrics_url = metrics_url or (
            self.base_url.replace("/v1", "/metrics").replace("/v1", "")
        )
        # /metrics is usually on the same host:port as the API server.
        if not metrics_url:
            host = self.base_url.split("//", 1)[1].split("/", 1)[0]
            self.metrics_url = f"http://{host}/metrics"
        self.timeout = timeout
        self.headers = {
            "Authorization": f"Bearer {api_key}" if api_key else ""
        }

    # ------------------------------------------------------------------
    async def _get_json(self, url: str) -> Optional[dict]:
        async with httpx.AsyncClient(timeout=httpx.Timeout(self.timeout)) as c:
            try:
                r = await c.get(url, headers=self.headers)
                if r.status_code == 200:
                    return r.json()
            except Exception:
                return None
        return None

    async def _get_text(self, url: str) -> Optional[str]:
        async with httpx.AsyncClient(timeout=httpx.Timeout(self.timeout)) as c:
            try:
                r = await c.get(url, headers=self.headers)
                if r.status_code == 200:
                    return r.text
            except Exception:
                return None
        return None

    # ------------------------------------------------------------------
    async def discover(self) -> EndpointMeta:
        meta = EndpointMeta(base_url=self.base_url)
        # 1. Model list
        models_url = f"{self.base_url}/models"
        models = await self._get_json(models_url)
        if models and "data" in models:
            data = models["data"]
            if self.model == "auto":
                meta.model = data[0].get("id", "") if data else ""
            else:
                meta.model = self.model
                # find matching entry for max_model_len
                for m in data:
                    if m.get("id") == self.model:
                        meta.model_max_len = m.get("max_model_len")
                        break
            # some servers expose max_model_len on the first entry
            if meta.model_max_len is None and data:
                meta.model_max_len = data[0].get("max_model_len")

        # 2. Version endpoint (vLLM /version, llama-server /v1/version or /version)
        for vpath in ("/version", "/v1/version", "/api/version"):
            base = self.base_url.split("/v1")[0]
            v = await self._get_json(f"{base}{vpath}")
            if v and isinstance(v, dict) and "version" in v:
                meta.version = v["version"]
                break
            vt = await self._get_text(f"{base}{vpath}")
            if vt:
                meta.version = vt.strip()
                break

        # 3. /metrics lines (first ~200 lines for engine hinting)
        mtext = await self._get_text(self.metrics_url)
        if mtext:
            lines = mtext.splitlines()
            meta.metrics_lines = lines[:400]
            # Engine hint from metric names
            joined = "\n".join(lines)
            if "vllm:" in joined:
                meta.engine_hints.append("vllm")
            if "llama" in joined.lower():
                meta.engine_hints.append("llamacpp")
            if "sglang:" in joined:
                meta.engine_hints.append("sglang")
            if "tgi_" in joined:
                meta.engine_hints.append("tgi")

        # 4. Process cmdline (if running locally / via ssh — best effort)
        from .processes import _list_candidate_pids
        for pid in _list_candidate_pids():
            try:
                with open(f"/proc/{pid}/cmdline", "rb") as f:
                    cmd = f.read().replace(b"\0", b" ").decode("utf-8", "replace")
                if any(k in cmd.lower() for k in ("vllm", "llama-server", "sglang", "trtllm")):
                    meta.proc_cmdline = cmd.split()
                    meta.engine_hints.append("proc-inspection")
                    break
            except Exception:
                continue

        return meta

    # ------------------------------------------------------------------
    def detect_engine(self, meta: EndpointMeta) -> tuple[str, EngineAdapter]:
        """Return (engine_name, adapter) via max-confidence detection."""
        if self.model == "auto" or True:
            best_name, best_adapter, best_score = "generic-openai", GenericAdapter(), 0.0
            for cls in ADAPTERS:
                adapter = cls()
                score = adapter.detect(meta.as_dict())
                if score > best_score:
                    best_name, best_adapter, best_score = adapter.name, adapter, score
            return best_name, best_adapter
        return "generic-openai", GenericAdapter()
