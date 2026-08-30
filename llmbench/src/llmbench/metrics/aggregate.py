"""Aggregate per-request RawRequests into CellMetrics (goal.md §18)."""

from __future__ import annotations

from typing import Optional

from ..schemas import (
    CellMetrics,
    RawRequest,
    WorkloadCell,
    compute_distribution,
)


def _mean(vals: list[float]) -> float:
    return sum(vals) / len(vals) if vals else 0.0


def aggregate_cell(
    requests: list[RawRequest],
    cell: WorkloadCell,
    cell_duration_s: float,
) -> CellMetrics:
    """Build CellMetrics from a list of RawRequests for one cell.

    Only completed (ok) requests contribute to throughput/latency; failed
    ones are counted for error rates.  All raw requests are preserved.
    """
    ok = [r for r in requests if r.ok]
    failed = [r for r in requests if not r.ok]
    n_total = len(requests)
    n_ok = len(ok)

    ttft = [r.ttft_s * 1000 for r in ok if r.ttft_s is not None]
    ttst = [r.ttst_s * 1000 for r in ok if r.ttst_s is not None]
    itls: list[float] = []
    for r in ok:
        itls.extend(r.inter_token_latencies_ms)
    # TPOT is per-request mean ITL (already per-request in RawRequest.tpot_ms)
    tpots = [r.tpot_ms for r in ok if r.tpot_ms is not None]
    req_lat = [r.request_latency_s * 1000 for r in ok]
    prefill_ms = [r.prefill_duration_s * 1000 for r in ok
                  if r.prefill_duration_s is not None]

    decode_tps = [r.decode_tps for r in ok if r.decode_tps is not None]
    prefill_tps = [r.prefill_tps for r in ok if r.prefill_tps is not None]

    # Throughput over the whole cell (aggregate, all streams)
    total_output_tokens = sum(r.output_tokens for r in ok)
    total_prompt_tokens = sum(r.input_tokens for r in ok if r.input_tokens > 0)
    if total_prompt_tokens == 0:
        total_prompt_tokens = sum(
            cell.input_tokens for r in ok
        )
    total_tokens = total_output_tokens + total_prompt_tokens

    output_tps = (total_output_tokens / cell_duration_s) if cell_duration_s > 0 else 0.0
    prompt_tps = (total_prompt_tokens / cell_duration_s) if cell_duration_s > 0 else 0.0
    total_tps = (total_tokens / cell_duration_s) if cell_duration_s > 0 else 0.0
    rps = (n_ok / cell_duration_s) if cell_duration_s > 0 else 0.0
    # per-user decode rate: mean per-request decode tps
    output_tps_per_user = _mean(decode_tps)

    # Error rates
    def rate(pred) -> float:
        return (sum(1 for r in failed if pred(r)) / n_total) if n_total else 0.0

    http_err = [r for r in failed if (r.error_kind or "").startswith("http")]
    timeout = [r for r in failed if r.error_kind == "timeout"]
    malformed = [r for r in failed
                 if r.error_kind in ("malformed_stream",)]
    incomplete = [r for r in ok if not r.completed_stream]
    overflow = [r for r in failed if r.error_kind == "context_overflow"]
    truncated = [r for r in ok if r.truncated]

    metrics = CellMetrics(
        ttft_ms=compute_distribution(ttft),
        ttst_ms=compute_distribution(ttst),
        itl_ms=compute_distribution(itls),
        tpot_ms=compute_distribution(tpots),
        request_latency_ms=compute_distribution(req_lat),
        prefill_duration_ms=compute_distribution(prefill_ms),
        output_tps=output_tps,
        request_rps=rps,
        prompt_tokens_per_s=prompt_tps,
        decode_tokens_per_s=_mean(decode_tps),
        total_tokens_per_s=total_tps,
        output_tps_per_user=output_tps_per_user,
        actual_input_tokens_mean=_mean([r.input_tokens for r in ok]),
        actual_output_tokens_mean=_mean([r.output_tokens for r in ok]),
        total_tokens_mean=_mean([r.total_tokens for r in ok]),
        error_rate=(len(failed) / n_total) if n_total else 0.0,
        http_error_rate=(len(http_err) / n_total) if n_total else 0.0,
        timeout_rate=(len(timeout) / n_total) if n_total else 0.0,
        malformed_stream_rate=(len(malformed) / n_total) if n_total else 0.0,
        incomplete_stream_rate=(len(incomplete) / n_total) if n_total else 0.0,
        context_overflow_rate=(len(overflow) / n_total) if n_total else 0.0,
        cancelled_rate=0.0,
        truncated_rate=(len(truncated) / n_total) if n_total else 0.0,
        completed_requests=n_ok,
        failed_requests=len(failed),
    )
    return metrics


def fill_network_stats(metrics: CellMetrics, network) -> None:
    if network is not None:
        metrics.network = network
