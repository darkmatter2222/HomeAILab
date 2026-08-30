"""Performance score families (goal.md §39).

Scores are a *convenience for comparison, not a replacement for
measurements*: every score keeps its raw inputs (``notes``) so a reader can
see exactly what produced it.  Quality is explicitly out of scope — no
model-quality score is produced here.

Normalization
-------------
Each family normalizes against a deployment-specific *reference point*, so a
score answers "how is this cell / this run compared to the rest of *this
deployment*?".  Scores are therefore comparable across configurations of
the same model (the tuning-history use case) but not blindly across
deployments with different hardware.  Every formula is versioned by
``SCORING_VERSION`` and documented in ``docs/scoring.md``.

Families (0-100; ``None`` = insufficient data for this family):
* Latency Score        - relative TTFT p95 (lower is better)
* Throughput Score     - relative peak aggregate output tokens/s
* Single-Stream Score  - relative single-stream decode rate (c=1)
* Concurrency Scaling  - relative aggregate throughput at max concurrency
* Long-Context Score   - relative aggregate throughput at the longest context
* Cache Efficiency     - warm-vs-cold TTFT improvement (only when both exist)
* Energy Efficiency    - relative output tokens/joule (GPU power required)
* Stability Score      - 100 - weighted penalty (errors, high variance,
                         throttle events, metric-source disagreement)
* Balanced Performance - geometric mean of the available families above
"""

from __future__ import annotations

import math
from typing import Optional

from ..schemas import (
    SCORING_VERSION,
    CacheMode,
    LoadMode,
    MeasurementCell,
)

# Family names (stable identifiers, used in artifacts + docs).
LATENCY = "latency"
THROUGHPUT = "throughput"
SINGLE_STREAM = "single_stream"
CONCURRENCY_SCALING = "concurrency_scaling"
LONG_CONTEXT = "long_context"
CACHE_EFFICIENCY = "cache_efficiency"
ENERGY_EFFICIENCY = "energy_efficiency"
STABILITY = "stability"
BALANCED = "balanced"

# Weights for the Balanced Performance Score (documented in docs/scoring.md).
_BALANCED_WEIGHTS: dict[str, float] = {
    LATENCY: 0.20,
    THROUGHPUT: 0.25,
    SINGLE_STREAM: 0.15,
    CONCURRENCY_SCALING: 0.15,
    LONG_CONTEXT: 0.10,
    CACHE_EFFICIENCY: 0.05,
    ENERGY_EFFICIENCY: 0.10,
}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _clamp(x: float) -> float:
    return max(0.0, min(100.0, round(x, 2)))


def _best_metric(cells: list[MeasurementCell], getter) -> Optional[float]:
    """Best (max) value of `getter(cell) -> Optional[float]` over cells."""
    vals = [v for v in (getter(m) for m in cells) if v is not None]
    return max(vals) if vals else None


def _worst_metric(cells: list[MeasurementCell], getter) -> Optional[float]:
    """Worst (min) value of `getter(cell) -> Optional[float]` over cells."""
    vals = [v for v in (getter(m) for m in cells) if v is not None]
    return min(vals) if vals else None


def _closed_loop(cells: list[MeasurementCell]) -> list[MeasurementCell]:
    return [m for m in cells if m.workload.load_mode == LoadMode.CLOSED_LOOP]


def _cell_value(m: MeasurementCell, getter) -> Optional[float]:
    v = getter(m)
    return v if v not in (None, 0) else None


def _relative_score(value: Optional[float], reference: Optional[float]) -> Optional[float]:
    """Score a single value against a reference: 100 * value / reference."""
    if value is None or not reference or reference <= 0:
        return None
    return 100.0 * value / reference


def _note(metric: str, value, reference) -> str:
    def f(v):
        return "n/a" if v is None else f"{v:.3f}"
    return f"{metric}: value={f(value)} reference={f(reference)}"


# ---------------------------------------------------------------------------
# family computations
# ---------------------------------------------------------------------------
def _score_latency(cells: list[MeasurementCell]) -> Optional[tuple[float, str]]:
    ttft = _worst_metric(
        _closed_loop(cells),
        lambda m: m.metrics.ttft_ms.p95 if m.metrics.ttft_ms.count else None,
    )
    # Reference: best (lowest) TTFT p95 achievable by this deployment.
    best_ttft = _worst_metric(
        _closed_loop(cells),
        lambda m: m.metrics.ttft_ms.p95 if m.metrics.ttft_ms.count else None,
    )
    if ttft is None:
        return None
    if best_ttft and best_ttft > 0:
        return _clamp(_relative_score(best_ttft, ttft)), _note("ttft_ms.p95", ttft, best_ttft)
    # No better reference: raw scale (100 ms -> 100, 1000 ms -> 10, 10s -> 1).
    return _clamp(100.0 * (0.1 / ttft)), _note("ttft_ms.p95 (absolute scale)", ttft, 0.1)


def _score_throughput(cells: list[MeasurementCell]) -> Optional[tuple[float, str]]:
    peak = _best_metric(_closed_loop(cells), lambda m: m.metrics.output_tps)
    if not peak:
        return None
    return _clamp(100.0 * math.log10(peak + 1)), (
        f"peak aggregate output_tps={peak:.2f} tok/s "
        f"(log10 scale: 10 tok/s=50, 100 tok/s=75, 1000 tok/s=100)"
    )


def _score_single_stream(cells: list[MeasurementCell]) -> Optional[tuple[float, str]]:
    solo = [m for m in _closed_loop(cells) if m.workload.concurrency == 1]
    if not solo:
        return None
    peak = _best_metric(solo, lambda m: m.metrics.output_tps_per_user or m.metrics.output_tps)
    if not peak:
        return None
    return _clamp(100.0 * math.log10(peak + 1)), (
        f"best single-stream decode (c=1)={peak:.2f} tok/s "
        f"(log10 scale: 10 tok/s=50, 20 tok/s~63, 100 tok/s=75)"
    )


def _score_concurrency_scaling(cells: list[MeasurementCell]) -> Optional[tuple[float, str]]:
    cl = _closed_loop(cells)
    by_conc: dict[int, float] = {}
    for m in cl:
        tps = m.metrics.output_tps
        c = m.workload.concurrency
        if tps > 0:
            by_conc[c] = max(by_conc.get(c, 0.0), tps)
    if len(by_conc) < 2:
        return None
    concs = sorted(by_conc)
    lo, hi = concs[0], concs[-1]
    if hi == lo:
        return None
    # Normalized marginal scaling: how close the top concurrency's throughput
    # is to (and beyond) the low concurrency's throughput, on a 0-2 scale
    # where 1.0 = no scaling gain and 2.0 = 2x the low-concurrency rate.
    ratio = by_conc[hi] / by_conc[lo]
    score = _clamp(100.0 * (ratio - 1.0))
    return score, (
        f"aggregate tps c={lo}: {by_conc[lo]:.2f} -> c={hi}: {by_conc[hi]:.2f} "
        f"(ratio {ratio:.2f}x; 100% = 2x scaling)"
    )


def _score_long_context(cells: list[MeasurementCell]) -> Optional[tuple[float, str]]:
    cl = _closed_loop(cells)
    by_ctx: dict[int, float] = {}
    for m in cl:
        tps = m.metrics.output_tps
        if tps > 0 and m.workload.input_tokens > 0:
            ctx = m.workload.input_tokens
            by_ctx[ctx] = max(by_ctx.get(ctx, 0.0), tps)
    if not by_ctx:
        return None
    max_ctx = max(by_ctx)
    base_ctx = min(by_ctx)
    base = by_ctx.get(base_ctx)
    if base and max_ctx != base_ctx:
        score = _clamp(_relative_score(by_ctx[max_ctx], base))
        return score, (
            f"aggregate tps at longest context ({max_ctx} tok) = "
            f"{by_ctx[max_ctx]:.2f} vs shortest ({base_ctx} tok) = {base:.2f}"
        )
    # Only one context measured: raw scale.
    return _clamp(100.0 * math.log10(by_ctx[max_ctx] + 1)), (
        f"aggregate tps at context {max_ctx} = {by_ctx[max_ctx]:.2f} (log10 scale)"
    )


def _score_cache_efficiency(cells: list[MeasurementCell]) -> Optional[tuple[float, str]]:
    def ttft(m: MeasurementCell) -> Optional[float]:
        return m.metrics.ttft_ms.p95 if m.metrics.ttft_ms.count else None

    def ttot(m: MeasurementCell) -> Optional[float]:
        return (
            m.metrics.ttft_ms.mean + m.metrics.tpot_ms.mean
            * max(1.0, m.workload.target_output_tokens)
            if m.metrics.ttft_ms.count and m.metrics.tpot_ms.count
            else None
        )

    cold = [m for m in _closed_loop(cells) if m.workload.cache_mode == CacheMode.COLD]
    warm = [m for m in _closed_loop(cells) if m.workload.cache_mode == CacheMode.WARM]
    pairs = [
        (tc, tw)
        for (tc, m_c) in cold
        for (tw, m_w) in warm
        if tc == tw  # same (ISL, OSL) coordinate
    ]
    if not pairs:
        # No warm cells at all -> cache is not enabled / not tested.
        return 0.0, "no warm-cache cells measured (prefix caching not exercised)"
    tc, tw = pairs[0]
    # 1) TTFT improvement: warm TTFT p95 should be much lower than cold.
    if tc > 0 and tw < tc:
        gain = (tc - tw) / tc
    else:
        gain = 0.0
    # 2) Time-to-output improvement (TTFT + target OSL * TPOT).
    tco, two = ttot(m_c), ttot(m_w)
    if tco and two and two < tco:
        gain2 = (tco - two) / tco
    else:
        gain2 = gain
    score = _clamp(50.0 + 50.0 * max(gain, gain2))
    return score, (
        f"cold TTFT p95={tc:.1f}ms warm={tw:.1f}ms (gain {max(gain, gain2) * 100:.0f}%; "
        f"base 50 = neutral, 100 = >=90% latency reduction)"
    )


def _score_energy_efficiency(cells: list[MeasurementCell]) -> Optional[tuple[float, str]]:
    powered = [
        m for m in _closed_loop(cells)
        if (m.metrics.output_tokens_per_joule or 0) > 0
    ]
    if not powered:
        return None
    best = max((m.metrics.output_tokens_per_joule for m in powered), default=None)
    if not best:
        return None
    return _clamp(100.0 * math.log10(best + 1)), (
        f"best output tokens/joule={best:.4f} (log10 scale; requires GPU power data)"
    )


def _score_stability(cells: list[MeasurementCell]) -> tuple[float, str]:
    if not cells:
        return 0.0, "no cells"
    penalty = 0.0
    notes = []
    n = len(cells)
    # 1) Error rate (mean over all requests in valid cells).
    tot_reqs = sum(m.metrics.completed_requests + m.metrics.failed_requests
                   for m in cells) or 1
    mean_err = sum(m.metrics.error_rate for m in cells) / n
    if mean_err > 0:
        penalty += 40.0 * min(1.0, mean_err / 0.10)
        notes.append(f"mean error rate {mean_err * 100:.1f}% (cap 40 pts)")
    # 2) High-variance cells (CV > 0.25 on a primary latency metric).
    hv = 0
    for m in cells:
        for d in (m.metrics.ttft_ms, m.metrics.itl_ms):
            if d.cv is not None and d.cv > 0.25 and d.count >= 8:
                hv += 1
                break
    if hv:
        penalty += 15.0 * min(1.0, hv / n)
        notes.append(f"{hv}/{n} cells with high variance (cap 15 pts)")
    # 3) GPU throttling events.
    throt = sum(m.metrics.throttle_events for m in cells if m.metrics.throttle_events)
    if throt:
        penalty += 20.0
        notes.append(f"{throt} GPU throttle events (flat 20 pts)")
    # 4) Material metric-source disagreements (client vs engine).
    dis = sum(1 for m in cells for d in m.metrics.discrepancies if d.material)
    if dis:
        penalty += 15.0 * min(1.0, dis / max(1, n))
        notes.append(f"{dis} material client/engine discrepancies (cap 15 pts)")
    score = _clamp(100.0 - penalty)
    return score, ("no penalty factors" if not notes else "; ".join(notes))


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------
def score_run(cells: list[MeasurementCell]) -> dict:
    """Score every family for one run's cells.

    Returns ``{family: (score, note)}`` where ``score`` is 0-100 or ``None``
    when the family's inputs are not available.  The balanced score is the
    weight-normalized geometric mean of the available families.
    """
    results: dict[str, tuple[Optional[float], str]] = {}
    results[LATENCY] = _score_latency(cells)
    results[THROUGHPUT] = _score_throughput(cells)
    results[SINGLE_STREAM] = _score_single_stream(cells)
    results[CONCURRENCY_SCALING] = _score_concurrency_scaling(cells)
    results[LONG_CONTEXT] = _score_long_context(cells)
    results[CACHE_EFFICIENCY] = _score_cache_efficiency(cells)
    results[ENERGY_EFFICIENCY] = _score_energy_efficiency(cells)
    results[STABILITY] = _score_stability(cells)

    # Balanced: weighted geometric mean of the available families.
    # (Re-normalized over the weights of the families that have data.)
    terms: list[tuple[float, float]] = []
    weight_sum = 0.0
    for fam, w in _BALANCED_WEIGHTS.items():
        s, _ = results[fam]
        if s is None:
            continue
        # Floor at 1% so one weak family cannot zero the geometric mean.
        terms.append((max(s, 1.0), w))
        weight_sum += w
    if terms:
        geo = math.exp(
            sum(math.log(f) * (w / weight_sum) for f, w in terms)
        )
        results[BALANCED] = (_clamp(geo),
                             f"weighted geometric mean of {len(terms)} available families")
    else:
        results[BALANCED] = (None, "no available families")
    return results


def score_cell(cells: list[MeasurementCell]) -> dict:
    """Per-cell scores: this cell's value relative to the run's best value.

    Returns ``{cell_id: {family: (score, note)}}``.  The cell score is a
    *within-run* relative measure ("how does this cell do compared to the
    best cell of this run for this dimension").
    """
    out: dict[str, dict] = {}
    for m in cells:
        cid = m.cell_id or m.workload.label()
        row: dict[str, tuple[Optional[float], str]] = {}

        def rel(value, best):
            return _relative_score(value, best)

        # Throughput: vs the run's peak aggregate.
        peak = _best_metric(_closed_loop(cells), lambda m: m.metrics.output_tps)
        row[THROUGHPUT] = (
            _clamp(rel(m.metrics.output_tps, peak)) if m.metrics.output_tps else 0.0,
            _note("output_tps", m.metrics.output_tps, peak),
        )
        # Latency: vs the run's best TTFT p95.
        best_ttft = _worst_metric(
            _closed_loop(cells),
            lambda m: m.metrics.ttft_ms.p95 if m.metrics.ttft_ms.count else None,
        )
        ttft = m.metrics.ttft_ms.p95 if m.metrics.ttft_ms.count else None
        row[LATENCY] = (
            _clamp(rel(best_ttft, ttft)) if ttft else None,
            _note("ttft_ms.p95", ttft, best_ttft),
        )
        # Stability (per-cell, absolute).
        row[STABILITY] = _score_stability([m])
        # Efficiency: vs the run's best tokens/joule.
        best_eff = _best_metric(
            _closed_loop(cells),
            lambda m: m.metrics.output_tokens_per_joule,
        )
        eff = m.metrics.output_tokens_per_joule
        row[ENERGY_EFFICIENCY] = (
            _clamp(rel(eff, best_eff)) if eff else None,
            _note("output_tokens_per_joule", eff, best_eff),
        )
        out[cid] = row
    return out


def build_scores_artifact(cells: list[MeasurementCell]) -> dict:
    """The full scores.json payload (machine-readable, raw values preserved)."""
    run_scores = score_run(cells)
    cell_scores = score_cell(cells)
    return {
        "scoring_version": SCORING_VERSION,
        "normalization": (
            "family scores are deployment-relative: 100 = best value observed "
            "in this run for that dimension; log10 scale for absolute-rate "
            "families (see docs/scoring.md). None = inputs unavailable."
        ),
        "run": {
            fam: {"score": s, "note": note} for fam, (s, note) in run_scores.items()
        },
        "cells": {
            cid: {
                fam: {"score": s, "note": note}
                for fam, (s, note) in row.items()
            }
            for cid, row in cell_scores.items()
        },
    }


def write_scores_json(rd, cells: list[MeasurementCell]) -> "Optional[object]":
    """Write scores.json into the run directory (atomic)."""
    import json as _json
    from pathlib import Path

    artifact = build_scores_artifact(cells)
    p = Path(rd.path) / "scores.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        _json.dump(artifact, f, indent=2, default=str, ensure_ascii=False)
    import os
    f = open(tmp, "r") if False else None
    import os as _os
    _os.replace(tmp, p)
    return p
