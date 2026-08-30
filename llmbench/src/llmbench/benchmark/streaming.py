"""Native OpenAI-compatible streaming benchmark engine (goal.md §3).

Independently calculates TTFT, ITL, TPOT, and throughput from streaming
responses.  This is the canonical measurement source — engine-reported
metrics are compared against it, never trusted blindly.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Optional

import httpx

from ..schemas import RawRequest
from ..security.sanitize import Sanitizer


@dataclass
class StreamConfig:
    model: str
    endpoint: str  # full URL, e.g. http://host:8000/v1/chat/completions
    is_chat: bool = True
    api_key: Optional[str] = None
    timeout_s: float = 300.0
    # Generation params
    temperature: float = 0.0
    max_tokens: int = 256
    stop: Optional[list[str]] = None
    ignore_eos: bool = False
    min_tokens: int = 0
    extra_body: dict[str, Any] = field(default_factory=dict)
    # stream_options: request usage in final chunk when the server supports it
    include_usage: bool = True


class StreamingClient:
    """Async httpx client for OpenAI-compatible streaming endpoints."""

    def __init__(self, sanitizer: Sanitizer | None = None) -> None:
        self._sanitizer = sanitizer or Sanitizer()
        self._client: httpx.AsyncClient | None = None

    _DEFAULT_TIMEOUT_S = 300.0

    async def __aenter__(self) -> "StreamingClient":
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(self._DEFAULT_TIMEOUT_S)
        )
        return self

    async def __aexit__(self, *exc) -> None:
        if self._client is not None:
            await self._client.aclose()

    def _ensure_client(self, timeout_s: float) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(timeout_s))
        return self._client

    # ------------------------------------------------------------------
    def _build_payload(
        self, cfg: StreamConfig, prompt_text: str, system: str | None
    ) -> tuple[str, dict]:
        if cfg.is_chat:
            messages = []
            if system:
                messages.append({"role": "system", "content": system})
            messages.append({"role": "user", "content": prompt_text})
            body: dict[str, Any] = {
                "model": cfg.model,
                "messages": messages,
                "stream": True,
                "max_tokens": cfg.max_tokens,
                "temperature": cfg.temperature,
            }
            if cfg.ignore_eos:
                body["ignore_eos"] = True
            if cfg.min_tokens:
                body["min_tokens"] = cfg.min_tokens
            if cfg.stop:
                body["stop"] = cfg.stop
            if cfg.extra_body:
                body.update(cfg.extra_body)
            if cfg.include_usage:
                body["stream_options"] = {"include_usage": True}
            return cfg.endpoint, body

        # /v1/completions
        body = {
            "model": cfg.model,
            "prompt": prompt_text,
            "stream": True,
            "max_tokens": cfg.max_tokens,
            "temperature": cfg.temperature,
        }
        if cfg.extra_body:
            body.update(cfg.extra_body)
        if cfg.include_usage:
            body["stream_options"] = {"include_usage": True}
        return cfg.endpoint, body

    # ------------------------------------------------------------------
    async def one_request(
        self,
        cfg: StreamConfig,
        prompt_text: str,
        request_id: str,
        system: str | None = None,
    ) -> RawRequest:
        """Issue one streaming request and return its RawRequest timings."""
        url, body = self._build_payload(cfg, prompt_text, system)
        client = self._ensure_client(cfg.timeout_s)
        headers = {}
        if cfg.api_key:
            headers["Authorization"] = f"Bearer {cfg.api_key}"

        rr = RawRequest(request_id=request_id)
        t_start = time.perf_counter()
        t_first_byte: Optional[float] = None
        t_first_token: Optional[float] = None
        t_prev_token: Optional[float] = None
        itls: list[float] = []
        completion_tokens = 0
        prompt_tokens = 0
        finish_reason: Optional[str] = None
        content_chars = 0
        completed = False
        usage_seen = False

        try:
            async with client.stream(
                "POST", url, json=body, headers=headers
            ) as resp:
                if resp.status_code != 200:
                    # Read a bit of the body for a diagnostic, then record.
                    try:
                        err_text = (await resp.aread())[:500].decode(
                            "utf-8", "replace"
                        )
                    except Exception:
                        err_text = ""
                    rr.http_status = resp.status_code
                    rr.ok = False
                    rr.completed_stream = False
                    rr.error_kind = _classify_http_error(resp.status_code, err_text)
                    rr.request_latency_s = time.perf_counter() - t_start
                    return rr

                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    line = line.strip()
                    if line.startswith(":"):  # SSE comment / keep-alive
                        continue
                    if not line.startswith("data:"):
                        continue
                    data = line[len("data:"):].strip()
                    if data == "[DONE]":
                        completed = True
                        break
                    try:
                        obj = json.loads(data)
                    except json.JSONDecodeError:
                        rr.completed_stream = False
                        continue

                    now = time.perf_counter()
                    if t_first_byte is None:
                        t_first_byte = now
                        rr.time_to_first_byte_s = now - t_start
                        rr.first_chunk_offset_s = now - t_start

                    # Handle usage (final chunk) when present
                    usage = obj.get("usage")
                    if usage:
                        usage_seen = True
                        prompt_tokens = usage.get("prompt_tokens", 0) or 0
                        completion_tokens = usage.get("completion_tokens", 0) or 0

                    # Extract the content delta
                    delta = _extract_delta(obj)
                    if delta:
                        content_chars += len(delta)
                        if t_first_token is None:
                            t_first_token = now
                            rr.ttft_s = now - t_start
                        else:
                            if t_prev_token is not None:
                                itls.append((now - t_prev_token) * 1000.0)
                            t_prev_token = now
                        # Count tokens: we count non-empty deltas as tokens
                        # (most engines emit one delta per token).
                        completion_tokens += 1

                    # finish reason (may appear in a non-streaming chunk)
                    fr = _extract_finish_reason(obj)
                    if fr:
                        finish_reason = fr

        except httpx.TimeoutException:
            rr.ok = False
            rr.completed_stream = False
            rr.error_kind = "timeout"
            rr.request_latency_s = time.perf_counter() - t_start
            return rr
        except httpx.HTTPError as e:
            rr.ok = False
            rr.completed_stream = False
            rr.error_kind = f"http_error:{type(e).__name__}"
            rr.request_latency_s = time.perf_counter() - t_start
            return rr
        except json.JSONDecodeError:
            rr.completed_stream = False
            rr.error_kind = "malformed_stream"

        rr.request_latency_s = time.perf_counter() - t_start
        rr.input_tokens = prompt_tokens
        rr.output_tokens = completion_tokens
        rr.total_tokens = prompt_tokens + completion_tokens
        rr.finish_reason = finish_reason
        rr.inter_token_latencies_ms = itls
        rr.completed_stream = completed or usage_seen
        rr.eos_seen = (finish_reason == "stop")
        rr.truncated = (finish_reason == "length")

        if rr.ok:
            if completion_tokens > 1 and t_prev_token and t_first_token:
                decode_dur = (t_prev_token - t_first_token)
                rr.decode_duration_s = decode_dur
                if decode_dur > 0:
                    rr.decode_tps = (completion_tokens - 1) / decode_dur
                    # TPOT is mean ITL
                    if itls:
                        rr.total_tps = (completion_tokens - 1) / decode_dur
                        # prefill
                        if t_first_token is not None:
                            prefill = t_first_token - t_start
                            if prefill > 0 and prompt_tokens > 0:
                                rr.prefill_tps = prompt_tokens / prefill
                                rr.prefill_duration_s = prefill
        return rr


def _extract_delta(obj: dict) -> str:
    """Pull the text delta out of an SSE chunk (chat or completions)."""
    if "choices" in obj and obj["choices"]:
        ch = obj["choices"][0]
        # chat
        delta = ch.get("delta")
        if isinstance(delta, dict):
            c = delta.get("content")
            if isinstance(c, str):
                return c
        # completions
        if isinstance(ch.get("text"), str):
            return ch["text"]
    return ""


def _extract_finish_reason(obj: dict) -> Optional[str]:
    if "choices" in obj and obj["choices"]:
        fr = obj["choices"][0].get("finish_reason")
        if isinstance(fr, str):
            return fr
    return None


def _classify_http_error(status: int, body: str) -> str:
    if status in (401, 403):
        return "auth_error"
    if status == 404:
        return "not_found"
    if status in (408, 504):
        return "timeout"
    if "context" in body.lower() or "too long" in body.lower() \
            or "max" in body.lower():
        return "context_overflow"
    if status >= 500:
        return "server_error"
    return f"http_{status}"
