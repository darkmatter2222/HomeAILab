"""Benchmark integrity — determine whether a measurement can be trusted
(goal.md §23).

Every cell receives a VALID / VALID_WITH_WARNINGS / INVALID verdict with
machine-readable reason codes.  Bad measurements are preserved and marked,
never silently discarded.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from ..schemas import (
    INVALID,
    REASON_EXTERNAL_GPU_PROCESS,
    REASON_HIGH_VARIANCE,
    REASON_INSUFFICIENT_SAMPLES,
    REASON_LOAD_GENERATOR_SATURATED,
    REASON_METRIC_SOURCE_DISAGREEMENT,
    REASON_OUTPUT_LENGTH_MISMATCH,
    REASON_POWER_THROTTLING,
    REASON_THERMAL_THROTTLING,
    VALID,
    VALID_WITH_WARNINGS,
    CellMetrics,
    IntegrityResult,
    IntegrityState,
    WorkloadCell,
)

# Thresholds (tunable)
HIGH_VARIANCE_CV = 0.25          # CV on a primary latency metric
MIN_SAMPLES = 8
# Below this number of samples a high CV is not statistically meaningful
# (it is "small sample", not "high variance").
MIN_SAMPLES_FOR_VARIANCE = 8
MISMATCH_TOLERANCE_PCT = 15.0   # client-vs-engine disagreement threshold
OUTPUT_LENGTH_TOLERANCE = 0.20  # actual/target OSL tolerance


@dataclass
class IntegrityInput:
    """Everything needed to judge a cell."""

    cell: WorkloadCell
    metrics: CellMetrics
    # GPU / pre-run signals
    pre_run_gpu_util_pct: Optional[float] = None
    pre_run_vram_used_gib: Optional[float] = None
    pre_run_external_gpu_proc: bool = False
    pre_run_throttled: bool = False
    # Run-time signals
    run_throttle_events: int = 0
    thermal_throttle_seen: bool = False
    power_throttle_seen: bool = False
    oom_seen: bool = False
    server_restart_seen: bool = False
    network_unstable: bool = False
    client_load_saturated: bool = False
    memory_pressure: bool = False
    clock_shift: bool = False
    # Cross-source disagreement flag
    metric_disagreement: bool = False
    # Pre-run (before this cell) server health
    health_ok: bool = True


def evaluate(inp: IntegrityInput) -> IntegrityResult:
    """Produce the IntegrityResult for a cell."""
    reasons: list[str] = []
    notes: list[str] = []
    invalid = False
    warning = False

    m = inp.metrics

    # --- hard INVALID conditions ---
    if inp.oom_seen:
        reasons.append("GPU_OOM")
        invalid = True
    if inp.server_restart_seen:
        reasons.append("SERVER_RESTART")
        invalid = True
    if inp.pre_run_external_gpu_proc and inp.pre_run_gpu_util_pct and inp.pre_run_gpu_util_pct > 30:
        reasons.append(REASON_EXTERNAL_GPU_PROCESS)
        warning = True  # external proc is a warning unless util is high
    if m.completed_requests < MIN_SAMPLES and m.error_rate < 0.5:
        reasons.append(REASON_INSUFFICIENT_SAMPLES)
        warning = True
    if m.completed_requests == 0:
        reasons.append(REASON_INSUFFICIENT_SAMPLES)
        invalid = True

    # High variance on TTFT / ITL (only judged when the sample size can
    # support a variance claim; otherwise it is INSUFFICIENT_SAMPLES).
    for dist_name in ("ttft_ms", "itl_ms"):
        dist = getattr(m, dist_name)
        if (dist.cv is not None and dist.cv > HIGH_VARIANCE_CV
                and dist.count >= MIN_SAMPLES_FOR_VARIANCE
                and m.completed_requests >= MIN_SAMPLES_FOR_VARIANCE):
            reasons.append(REASON_HIGH_VARIANCE)
            notes.append(f"high CV on {dist_name} ({dist.cv:.2f})")
            warning = True
            break

    # Output length mismatch
    if inp.cell.target_output_tokens > 0:
        ratio = m.actual_output_tokens_mean / inp.cell.target_output_tokens
        if ratio < (1.0 - OUTPUT_LENGTH_TOLERANCE):
            reasons.append(REASON_OUTPUT_LENGTH_MISMATCH)
            notes.append(
                f"actual OSL mean {m.actual_output_tokens_mean:.0f} "
                f"vs target {inp.cell.target_output_tokens}"
            )
            warning = True

    # Throttling
    if inp.thermal_throttle_seen or (inp.run_throttle_events and "thermal" in str(getattr(m, "throttle_reasons_sample", ""))):
        reasons.append(REASON_THERMAL_THROTTLING)
        warning = True
    if inp.power_throttle_seen:
        reasons.append(REASON_POWER_THROTTLING)
        warning = True

    # Network / client-side
    if inp.network_unstable:
        reasons.append("NETWORK_UNSTABLE")
        warning = True
    if inp.client_load_saturated:
        reasons.append(REASON_LOAD_GENERATOR_SATURATED)
        warning = True
    if inp.memory_pressure:
        reasons.append("MEMORY_PRESSURE")
        warning = True
    if inp.clock_shift:
        reasons.append("CLOCK_SHIFT")
        warning = True

    # Cross-source disagreement
    for d in m.discrepancies:
        if d.material:
            reasons.append(REASON_METRIC_SOURCE_DISAGREEMENT)
            notes.append(
                f"client vs engine disagree on {d.metric} "
                f"({d.client_value:.2f} vs {d.engine_value:.2f}, "
                f"{d.relative_error_pct:.1f}%)"
            )
            warning = True
            break

    if invalid:
        state = IntegrityState.INVALID
    elif warning:
        state = IntegrityState.VALID_WITH_WARNINGS
    else:
        state = IntegrityState.VALID

    return IntegrityResult(state=state, reasons=reasons, notes=notes)


def overall_state(results: list[IntegrityResult]) -> str:
    """Aggregate cell integrity to a run-level state."""
    if not results:
        return VALID
    worst = VALID
    any_invalid = any(r.state == IntegrityState.INVALID for r in results)
    any_warn = any(r.state == IntegrityState.VALID_WITH_WARNINGS for r in results)
    if any_invalid:
        # A run with even one INVALID cell is still "valid with warnings"
        # at the run level unless the majority is invalid.
        n_invalid = sum(1 for r in results if r.state == IntegrityState.INVALID)
        if n_invalid > len(results) / 2:
            worst = INVALID
        else:
            worst = VALID_WITH_WARNINGS
    elif any_warn:
        worst = VALID_WITH_WARNINGS
    return worst


def reason_codes(results: list[IntegrityResult]) -> list[str]:
    seen: list[str] = []
    for r in results:
        for code in r.reasons:
            if code not in seen:
                seen.append(code)
    return seen
