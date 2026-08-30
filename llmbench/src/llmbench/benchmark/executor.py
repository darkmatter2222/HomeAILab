"""Benchmark cell executor (goal.md §29, §41, §45, §47).

The executor runs one ``WorkloadCell`` end-to-end:
generate prompts (cold/warm per cache mode) -> drive the load generator
(closed or open loop) -> issue streaming requests -> sample GPU telemetry in
parallel -> aggregate into ``CellMetrics`` -> cross-validate against engine
metrics -> judge integrity -> persist an immutable ``MeasurementCell`` +
checkpoint.

The executor is the *child*: it measures an already-running deployment and
never restarts or reconfigures it (goal.md §4).
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from ..schemas import (
    CacheMode,
    CellMetrics,
    Discrepancy,
    LoadMode,
    MeasurementCell,
    MeasurementSource,
    RawRequest,
    WorkloadCell,
    utc_now,
)
from ..security.sanitize import Sanitizer
from ..telemetry.gpu import GpuTelemetry, GpuTelemetryConfig
from ..workloads.loader import ClosedLoopGenerator, OpenLoopGenerator
from ..workloads.prompts import generate_prompt
from ..metrics.aggregate import aggregate_cell
from .streaming import StreamingClient, StreamConfig
from ..discovery.prometheus import PrometheusScraper, metric_value
from ..adapters.base import EngineAdapter


@dataclass
class ExecutorConfig:
    """Runtime options for the executor (goal.md §4, §29, §45)."""

    endpoint: str                    # base, e.g. http://host:8006/v1
    model: str                       # model name sent in the payload
    api_key: Optional[str] = None
    is_chat: bool = True
    ignore_eos: bool = False
    min_tokens: int = 0
    timeout_s: float = 300.0
    # Repetitions: how many distinct prompts per closed-loop cell.  The
    # canonical "repetitions" of a cell is its distinct-prompt count; each
    # prompt is issued as a separate request so the cell has enough samples
    # for meaningful distributions.
    samples_per_cell: int = 8
    warm_prefix_frac: float = 0.5    # fraction of a warm prompt that is a shared prefix
    # Telemetry
    gpu_telemetry: bool = True
    gpu_ssh_host: Optional[str] = None
    gpu_ssh_user: Optional[str] = None
    gpu_ssh_key: Optional[str] = None
    gpu_index: int = 0
    sample_interval_s: float = 1.0
    # Cross-validation
    metrics_url: Optional[str] = None
    adapter: Optional[EngineAdapter] = None
    # Where to persist
    run_dir: Optional[Any] = None    # a storage.run_dir.RunDirectory
    sanitizer: Sanitizer = field(default_factory=Sanitizer)
    # Pre-run environment probes (integrity context, goal.md §23)
    pre_run_gpu_util_pct: Optional[float] = None
    pre_run_external_gpu_proc: bool = False


class CellExecutor:
    """Runs a single measurement cell and returns a persisted MeasurementCell."""

    def __init__(self, cfg: ExecutorConfig) -> None:
        self.cfg = cfg
        self._sanitizer = cfg.sanitizer

    # ------------------------------------------------------------------
    def _endpoint_url(self) -> str:
        base = self.cfg.endpoint.rstrip("/")
        return f"{base}/chat/completions" if self.cfg.is_chat else f"{base}/completions"

    # ------------------------------------------------------------------
    def _make_stream_cfg(self, cell: WorkloadCell) -> StreamConfig:
        return StreamConfig(
            model=self.cfg.model,
            endpoint=self._endpoint_url(),
            is_chat=self.cfg.is_chat,
            api_key=self.cfg.api_key,
            timeout_s=self.cfg.timeout_s,
            max_tokens=cell.target_output_tokens,
            ignore_eos=self.cfg.ignore_eos,
            min_tokens=self.cfg.min_tokens,
        )

    # ------------------------------------------------------------------
    def _prompt_for(self, cell: WorkloadCell, rep: int) -> str:
        """Cold: unique prompt per repetition. Warm: shared prefix reused."""
        seed = hash(cell.key()) & 0x7FFFFFFF
        if cell.cache_mode == CacheMode.WARM:
            # Reuse the same prompt across repetitions within this cell to
            # build a warm KV prefix (variant fixed, repetition fixed=0).
            from ..workloads.prompts import warm_prefix_prompt
            prefix = int(cell.input_tokens * self.cfg.warm_prefix_frac)
            spec = warm_prefix_prompt(
                target_tokens=cell.input_tokens,
                prefix_tokens=prefix,
                variant=seed,
            )
            return spec.text
        spec = generate_prompt(
            target_tokens=cell.input_tokens,
            cell_seed=seed,
            repetition=rep,
            variant=rep,
        )
        return spec.text

    # ------------------------------------------------------------------
    async def _run_cell(self, cell: WorkloadCell) -> MeasurementCell:
        n_samples = self.cfg.samples_per_cell * cell.repetitions
        requests: list[RawRequest] = []
        prompts = [self._prompt_for(cell, rep) for rep in range(n_samples)]
        prompt_iter = iter(range(n_samples))
        next_prompt_idx = 0

        started = utc_now()
        t0 = time.perf_counter()

        # GPU telemetry in the background
        gpu = None
        if self.cfg.gpu_telemetry:
            gtc = GpuTelemetryConfig(
                sample_interval_s=self.cfg.sample_interval_s,
                mode="ssh" if self.cfg.gpu_ssh_host else "auto",
                ssh_host=self.cfg.gpu_ssh_host,
                ssh_user=self.cfg.gpu_ssh_user,
                ssh_key=self.cfg.gpu_ssh_key,
                gpu_index=self.cfg.gpu_index,
            )
            gpu = GpuTelemetry(gtc, self._sanitizer)
            await gpu.start()

        # Pre-capture engine metrics (for deltas / cross-validation)
        pre_metrics = self._scrape_metrics()

        async def issue_one() -> None:
            nonlocal next_prompt_idx
            idx = next_prompt_idx
            next_prompt_idx += 1
            prompt = prompts[idx % len(prompts)]
            scfg = self._make_stream_cfg(cell)
            async with StreamingClient(self._sanitizer) as client:
                rr = await client.one_request(
                    scfg, prompt, request_id=f"{cell.cell_id or cell.label()}:{idx}"
                )
                rr.target_output_tokens = cell.target_output_tokens
                requests.append(rr)

        stop = asyncio.Event()
        generator = self._make_generator(cell)
        await generator.run(issue_one, stop)

        # Stop GPU telemetry
        series = None
        if gpu is not None:
            series = await gpu.stop()

        # Post-capture engine metrics (window = [pre, post]).
        post_metrics = self._scrape_metrics()

        duration = time.perf_counter() - t0
        metrics = aggregate_cell(requests, cell, duration)
        self._fill_efficiency(metrics, requests, duration, gpu)
        self._fill_gpu_snapshot(metrics, gpu)
        self._cross_validate(cell, metrics, pre_metrics, post_metrics)

        # Integrity
        from ..integrity.check import IntegrityInput, evaluate
        integ_input = IntegrityInput(
            cell=cell,
            metrics=metrics,
            pre_run_gpu_util_pct=self.cfg.pre_run_gpu_util_pct,
            pre_run_external_gpu_proc=self.cfg.pre_run_external_gpu_proc,
        )
        integ = evaluate(integ_input)

        finished = utc_now()
        mc = MeasurementCell(
            cell_id=cell.cell_id or f"{cell.key()}",
            workload=cell,
            started_at=started,
            finished_at=finished,
            duration_s=duration,
            metrics=metrics,
            integrity=integ,
            sources=[
                MeasurementSource(name="client-observed", origin="client-observed",
                                   endpoint=self.cfg.endpoint),
                MeasurementSource(name="gpu-telemetry",
                                   origin="gpu-telemetry",
                                   endpoint=(series.source if series else "nvidia-smi")),
            ],
            raw_requests=requests,
        )
        self._persist(mc, series if gpu else None)
        return mc

    def _make_generator(self, cell: WorkloadCell):
        if cell.load_mode == LoadMode.CLOSED_LOOP:
            return ClosedLoopGenerator(
                concurrency=max(1, cell.concurrency),
                total_requests=self.cfg.samples_per_cell * cell.repetitions,
            )
        rate = cell.arrival_rate or 1.0
        pattern = "poisson" if cell.load_mode == LoadMode.OPEN_LOOP_POISSON else "constant"
        return OpenLoopGenerator(
            rate=rate,
            pattern=pattern,
            total_requests=self.cfg.samples_per_cell * cell.repetitions,
        )

    # ------------------------------------------------------------------
    def _scrape_metrics(self) -> Optional[dict]:
        if not self.cfg.metrics_url or self.cfg.adapter is None:
            return None
        scraper = PrometheusScraper(self.cfg.metrics_url)
        return scraper.scrape()

    def _cross_validate(self, cell: WorkloadCell, metrics: CellMetrics,
                        pre_metrics: Optional[dict],
                        post_metrics: Optional[dict]) -> None:
        """Compare client-observed vs engine-reported; surface disagreements (§47).

        Uses a pre/post scrape window when possible; degrades gracefully to
        a single snapshot when only one is available.
        """
        if self.cfg.adapter is None:
            return
        if pre_metrics is None and post_metrics is None:
            return
        mapping = self.cfg.adapter.metric_mapping()
        discrepancies: list[Discrepancy] = []

        def _series_value(met: Optional[dict], name: str, agg: str) -> Optional[float]:
            if met is None:
                return None
            return metric_value(met, name, aggregate=agg)

        def _window(name: str, agg: str) -> Optional[float]:
            """Value over the [pre, post] window for a counter/histogram."""
            pre = _series_value(pre_metrics, name, agg)
            post = _series_value(post_metrics, name, agg)
            if pre is None and post is None:
                return None
            if pre is not None and post is not None:
                if agg == "sum":
                    d = post - pre
                    return d if d >= 0 else None  # counter reset
                # for mean/max on gauges, use the post value
                return post
            return pre if pre is not None else post

        # Engine TTFT (seconds) vs client TTFT (ms).  The canonical key is
        # "ttft_s"; tolerate "ttft" and fall back to the vLLM metric name.
        ttft_metric = (
            mapping.get("ttft_s")
            or mapping.get("ttft")
            or "vllm:time_to_first_token_seconds"
        )
        # TTFT histograms/counters: sum over the cell window.
        ttft_engine = _window(ttft_metric, "sum")
        if ttft_engine is None:
            ttft_engine = _window(ttft_metric, "mean")
        if ttft_engine is not None and metrics.ttft_ms.count > 0:
            client_v = metrics.ttft_ms.mean
            engine_v_ms = ttft_engine * 1000.0
            rel = _relative_error(client_v, engine_v_ms)
            if rel > 0.25:
                discrepancies.append(Discrepancy(
                    metric="ttft", client_value=client_v,
                    engine_value=engine_v_ms,
                    engine_source="engine-metrics",
                    relative_error_pct=rel * 100,
                    material=True,
                ))

        # ITL cross-check when the engine exposes it.
        itl_metric = mapping.get("itl_s") or "vllm:inter_token_latency_seconds"
        itl_engine = _window(itl_metric, "mean")
        if (itl_engine is not None and metrics.itl_ms.count > 0
                and metrics.itl_ms.mean > 0):
            client_v = metrics.itl_ms.mean
            engine_v_ms = itl_engine * 1000.0
            rel = _relative_error(client_v, engine_v_ms)
            if rel > 0.25:
                discrepancies.append(Discrepancy(
                    metric="itl", client_value=client_v,
                    engine_value=engine_v_ms,
                    engine_source="engine-metrics",
                    relative_error_pct=rel * 100,
                    material=True,
                ))
        metrics.discrepancies.extend(discrepancies)

    def _fill_efficiency(self, metrics: CellMetrics, requests: list[RawRequest],
                        duration: float, gpu: Optional[GpuTelemetry]) -> None:
        if gpu is None:
            return
        avg_power, peak_power = gpu.power_summary()
        energy = gpu.energy_joule()
        metrics.avg_power_watts = avg_power
        metrics.peak_power_watts = peak_power
        metrics.energy_joule = energy
        out_tokens = sum(r.output_tokens for r in requests if r.ok)
        total_tokens = sum(r.total_tokens for r in requests if r.ok)
        n_ok = sum(1 for r in requests if r.ok)
        if energy and energy > 0:
            if out_tokens > 0:
                metrics.output_tokens_per_joule = out_tokens / energy
                metrics.joules_per_output_token = energy / out_tokens
            if total_tokens > 0:
                metrics.total_tokens_per_joule = total_tokens / energy
            if n_ok > 0:
                metrics.joules_per_request = energy / n_ok
        if avg_power and avg_power > 0:
            metrics.output_tps_per_watt = metrics.output_tps / avg_power
            metrics.requests_per_watt = metrics.request_rps / avg_power

    def _fill_gpu_snapshot(self, metrics: CellMetrics, gpu: Optional[GpuTelemetry]) -> None:
        if gpu is None:
            return
        s = gpu.gpu_summary()
        metrics.gpu_utilization_pct_mean = s.get("gpu_utilization_pct_mean")
        metrics.gpu_utilization_pct_max = s.get("gpu_utilization_pct_max")
        metrics.vram_used_gib_max = s.get("vram_used_gib_max")
        metrics.gpu_temp_c_mean = s.get("gpu_temp_c_mean")
        metrics.gpu_temp_c_max = s.get("gpu_temp_c_max")
        metrics.sm_clock_mhz_mean = s.get("sm_clock_mhz_mean")
        metrics.sm_clock_mhz_max = s.get("sm_clock_mhz_max")
        metrics.mem_clock_mhz_mean = s.get("mem_clock_mhz_mean")
        metrics.throttle_events = s.get("throttle_events", 0)

    # ------------------------------------------------------------------
    def _persist(self, mc: MeasurementCell, series) -> None:
        if self.cfg.run_dir is None:
            return
        rd = self.cfg.run_dir
        cell_id = mc.cell_id or "cell"
        rd.atomic_write_json(
            rd.path / "raw" / f"{cell_id}.json", mc.model_dump(mode="json")
        )
        if series is not None and series.samples:
            rd.atomic_write_json(
                rd.path / "telemetry" / f"{cell_id}.json",
                series.model_dump(mode="json"),
            )

    # ------------------------------------------------------------------
    async def run_cell(self, cell: WorkloadCell) -> MeasurementCell:
        return await self._run_cell(cell)


def _relative_error(a: float, b: float) -> float:
    if b == 0:
        return 0.0 if a == 0 else float("inf")
    return abs(a - b) / abs(b)
