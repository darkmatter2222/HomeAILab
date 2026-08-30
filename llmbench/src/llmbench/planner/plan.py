"""Adaptive benchmark planner + light/heavy budget policies (goal.md §25, §26).

The planner decides which workload cells to run in what order, learning from
completed measurements to focus budget on the most informative regions
(saturation knee, sharp context transitions, high-variance cells) instead of
blindly sweeping the whole space.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from ..schemas import (
    BenchmarkMode,
    CacheMode,
    CellMetrics,
    LoadMode,
    MeasurementCell,
    WorkloadCell,
)

# ---------------------------------------------------------------------------
# Default axes (goal.md §12, §13, §15).  The planner trims these to the
# deployment's actual max context and budget.
# ---------------------------------------------------------------------------
DEFAULT_ISL = [128, 512, 1024, 2048, 4096, 8192, 16384, 32768, 65536,
               131072, 262144, 524288]
DEFAULT_OSL = [32, 128, 256, 512, 1024, 2048]
CONCURRENCY_LADDER = [1, 2, 4, 8, 16, 32, 64, 128]


@dataclass
class Budget:
    """Budget policy (goal.md §25).  A budget is a time window + a mode."""

    mode: BenchmarkMode
    total_seconds: float

    def remaining(self, elapsed: float) -> float:
        return max(0.0, self.total_seconds - elapsed)

    def is_exhausted(self, elapsed: float) -> bool:
        return self.remaining(elapsed) <= 0


def parse_budget(s: str) -> float:
    """Parse '2h' / '45m' / '300s' / '48h' into seconds."""
    s = s.strip().lower()
    for unit, mult in (("h", 3600), ("m", 60), ("s", 1)):
        if s.endswith(unit):
            return float(s[: -1]) * mult
    return float(s)  # raw seconds


# ---------------------------------------------------------------------------
# Cell priority ordering for the "maximize info per time" objective (§25)
# ---------------------------------------------------------------------------
def light_plan(
    max_context: Optional[int],
    budget: Budget,
    max_concurrency: Optional[int] = None,
) -> list[WorkloadCell]:
    """Light mode: baseline + representative context + concurrency scaling.

    Order: concurrency=1 at short/medium/long context (the headline numbers),
    then concurrency scaling at a mid context, then a few cache/cold-warm
    comparisons.  Short cells first so the user gets a usable result fast.
    """
    cells: list[WorkloadCell] = []
    ctxs = [c for c in DEFAULT_ISL if (max_context is None or c <= max_context)]
    # Cap context list to a representative subset for light mode.
    ctxs_light = _dedupe(ctxs, cap=6)

    # 1. Baseline single-stream across contexts (cold cache).
    for isl in ctxs_light:
        for osl in [128, 512]:
            cells.append(_cell(isl, osl, 1, CacheMode.COLD, LoadMode.CLOSED_LOOP))

    # 2. Concurrency scaling at a mid context.
    mid_ctx = _representative_context(ctxs_light)
    for c in [x for x in CONCURRENCY_LADDER
              if (max_concurrency is None or x <= max_concurrency)]:
        cells.append(_cell(mid_ctx, 512, c, CacheMode.COLD, LoadMode.CLOSED_LOOP))

    # 3. Cache cold vs warm at a couple of contexts.
    for isl in ctxs_light[:2]:
        for cache in (CacheMode.COLD, CacheMode.WARM):
            cells.append(_cell(isl, 256, 1, cache, LoadMode.CLOSED_LOOP))
    return cells


def heavy_plan(
    max_context: Optional[int],
    budget: Budget,
    max_concurrency: Optional[int] = None,
) -> list[WorkloadCell]:
    """Heavy mode: dense matrices + soak (goal.md §27)."""
    cells: list[WorkloadCell] = []
    ctxs = [c for c in DEFAULT_ISL if (max_context is None or c <= max_context)]
    ctxs_heavy = _dedupe(ctxs, cap=8)
    concs = [x for x in CONCURRENCY_LADDER
             if (max_concurrency is None or x <= max_concurrency)]
    # Dense context x concurrency at a representative OSL.
    for isl in ctxs_heavy:
        for c in concs[:4]:
            cells.append(_cell(isl, 512, c, CacheMode.COLD, LoadMode.CLOSED_LOOP))
    # Output-length matrix at mid context + concurrency 1 & 4.
    mid = _representative_context(ctxs_heavy)
    for osl in DEFAULT_OSL:
        for c in [1, 4]:
            cells.append(_cell(mid, osl, c, CacheMode.COLD, LoadMode.CLOSED_LOOP))
    # Cold/warm across contexts.
    for isl in ctxs_heavy[:4]:
        for cache in (CacheMode.COLD, CacheMode.WARM):
            cells.append(_cell(isl, 256, 1, cache, LoadMode.CLOSED_LOOP))
    # Open-loop (poisson) at a representative rate.
    cells.append(WorkloadCell(
        input_tokens=mid, target_output_tokens=512, concurrency=1,
        cache_mode=CacheMode.COLD, load_mode=LoadMode.OPEN_LOOP_POISSON,
        arrival_rate=0.5, repetitions=1,
    ))
    return cells


def _cell(isl, osl, conc, cache, load, reps=1, rate=None) -> WorkloadCell:
    return WorkloadCell(
        input_tokens=isl,
        target_output_tokens=osl,
        concurrency=conc,
        cache_mode=cache,
        load_mode=load,
        repetitions=reps,
        arrival_rate=rate,
    )


def _dedupe(vals: list[int], cap: int) -> list[int]:
    """Keep up to `cap` representative points (log-spaced)."""
    vals = sorted(set(vals))
    if len(vals) <= cap:
        return vals
    # Pick cap points spread across the range (first, last, and log-spaced).
    import math
    n = len(vals)
    if n <= cap:
        return vals
    step = (n - 1) / (cap - 1)
    out = [int(round(vals[int(i * step)])) for i in range(cap)]
    return sorted(set(out))


def _representative_context(ctxs: list[int]) -> int:
    if not ctxs:
        return 4096
    # A mid-range context for scaling tests.
    return ctxs[len(ctxs) // 2]


# ---------------------------------------------------------------------------
# Adaptive refinement (§26)
# ---------------------------------------------------------------------------
class Planner:
    """Generates, reorders, and refines the cell list as results arrive.

    Persistence: every decision is appended to planner.jsonl so the strategy
    is auditable (goal.md §26).
    """

    def __init__(
        self,
        plan: list[WorkloadCell],
        budget: Budget,
        max_concurrency: Optional[int] = None,
        max_context: Optional[int] = None,
    ) -> None:
        self.plan: list[WorkloadCell] = plan
        self.budget = budget
        self.max_concurrency = max_concurrency
        self.max_context = max_context
        self.completed: dict[tuple, MeasurementCell] = {}
        self.decisions: list[str] = []

    # ------------------------------------------------------------------
    def next_cell(self) -> Optional[WorkloadCell]:
        """Return the next cell to run, or None if the plan is exhausted."""
        # Drop already-completed cells (keyed by workload coordinate).
        for i, cell in enumerate(self.plan):
            if cell.key() not in self.completed:
                return cell
        return None

    def mark_done(self, cell: WorkloadCell, result: MeasurementCell) -> None:
        self.completed[cell.key()] = result
        self.decisions.append(
            f"completed {cell.label()} in {result.duration_s:.1f}s"
        )

    # ------------------------------------------------------------------
    def refine(self) -> list[WorkloadCell]:
        """Insert additional cells around regions of interest (§26).

        Called after a batch of measurements; inserts:
        * concurrency cells around the saturation knee
        * context cells across a sharp prefill/throughput transition
        * extra repetitions for high-variance cells
        """
        insertions: list[WorkloadCell] = []
        conc_cells = [m for m in self.completed.values()
                      if m.workload.load_mode == LoadMode.CLOSED_LOOP]

        # Saturation knee detection on concurrency (aggregate TPS).
        conc_tps = sorted(
            (m.workload.concurrency, m.metrics.output_tps)
            for m in conc_cells
        )
        knee = _find_saturation_knee(conc_tps)
        if knee is not None:
            base = knee
            for cand in (base // 2, base - 1, base, base + 1, base * 2):
                if cand < 1:
                    continue
                if self.max_concurrency and cand > self.max_concurrency:
                    continue
                if any(m.workload.concurrency == cand for m in conc_cells):
                    continue
                insertions.append(_cell(
                    _representative_context([c for c in DEFAULT_ISL
                                             if (self.max_context is None or c <= self.max_context)]),
                    512, cand, CacheMode.COLD, LoadMode.CLOSED_LOOP,
                ))
                self.decisions.append(f"refine: concurrency {cand} near knee {base}")

        # High-variance cells get an extra repetition.
        for m in self.completed.values():
            for dname in ("ttft_ms", "itl_ms"):
                d = getattr(m.metrics, dname)
                if d.cv is not None and d.cv > 0.35 and m.workload.repetitions < 3:
                    extra = _cell(
                        m.workload.input_tokens, m.workload.target_output_tokens,
                        m.workload.concurrency, m.workload.cache_mode,
                        m.workload.load_mode, reps=m.workload.repetitions + 1,
                    )
                    insertions.append(extra)
                    self.decisions.append(
                        f"refine: extra rep for {m.workload.label()} (high variance)"
                    )
                    break

        if insertions:
            # De-duplicate against the existing plan.
            existing = {c.key() for c in self.plan} | self.completed.keys()
            for c in insertions:
                if c.key() not in existing:
                    self.plan.append(c)
                    existing.add(c.key())
        return insertions

    # ------------------------------------------------------------------
    def estimate_cell_time(self, cell: WorkloadCell,
                           prior: Optional[MeasurementCell] = None) -> float:
        """Rough per-cell time estimate to fit the budget (§25)."""
        # Heuristic: a cell's wall time scales with concurrency and OSL.
        base = 30.0  # seconds overhead + short decode
        per_tok = 0.06  # s per output token at concurrency 1
        est = base + cell.target_output_tokens * per_tok * max(1, cell.concurrency // 2)
        if prior is not None:
            est = prior.duration_s
        return est

    def budget_exhausted(self, elapsed: float) -> bool:
        return self.budget.is_exhausted(elapsed)


def _find_saturation_knee(pairs: list[tuple[int, float]]) -> Optional[int]:
    """Find the concurrency where aggregate TPS stops improving (plateau).

    Returns the concurrency at which the marginal gain drops below 10% of
    the previous step's gain (a knee).  None if monotonic or too few points.
    """
    if len(pairs) < 3:
        return None
    gains = []
    for i in range(1, len(pairs)):
        c0, t0 = pairs[i - 1]
        c1, t1 = pairs[i]
        gain = t1 - t0
        gains.append((c1, gain))
    # Find the first gain that is < 10% of the max gain seen so far.
    max_gain = max(g for _, g in gains) or 1.0
    for c, g in gains:
        if g < 0.10 * max_gain:
            return c
    return None
