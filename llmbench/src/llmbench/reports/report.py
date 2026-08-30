"""Run-report generation (goal.md §32, §34, §35, §48, §49, §51, §52).

Produces, inside the run directory:
* ``summary.json``  - headline KPIs + per-cell table
* ``integrity.json``- integrity verdicts + reason codes
* ``metrics.csv``   - machine-readable per-cell metrics
* ``metrics.json``  - machine-readable full metrics
* ``measurements.parquet`` - parquet export (when pyarrow available)
* ``index.html``    - a self-contained Plotly HTML dashboard

All JSON is written *after* sanitization (secrets already redacted at the
source by the executor / CLI).  HTML is a single file (inlined CSS/JS) so it
can be copied anywhere.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..schemas import (
    MeasurementCell,
    RunManifest,
    SummaryKpis,
    REPORT_GENERATOR_VERSION,
)
from ..security.sanitize import Sanitizer


# ---------------------------------------------------------------------------
# Machine-readable exports
# ---------------------------------------------------------------------------
def _cell_row(m: MeasurementCell) -> dict:
    """A flat dict of the cell's headline metrics (CSV/JSON friendly)."""
    mt = m.metrics
    return {
        "cell_id": m.cell_id,
        "input_tokens": m.workload.input_tokens,
        "target_output_tokens": m.workload.target_output_tokens,
        "concurrency": m.workload.concurrency,
        "cache_mode": m.workload.cache_mode.value,
        "load_mode": m.workload.load_mode.value,
        "arrival_rate": m.workload.arrival_rate,
        "integrity_state": m.integrity.state.value,
        "integrity_reasons": ";".join(m.integrity.reasons),
        "output_tps": round(mt.output_tps, 3),
        "output_tps_per_user": round(mt.output_tps_per_user, 3),
        "total_tokens_per_s": round(mt.total_tokens_per_s, 3),
        "request_rps": round(mt.request_rps, 4),
        "ttft_ms_mean": round(mt.ttft_ms.mean, 2) if mt.ttft_ms.count else None,
        "ttft_ms_p95": round(mt.ttft_ms.p95, 2) if mt.ttft_ms.count else None,
        "ttft_ms_p99": round(mt.ttft_ms.p99, 2) if mt.ttft_ms.count else None,
        "itl_ms_mean": round(mt.itl_ms.mean, 3) if mt.itl_ms.count else None,
        "itl_ms_p95": round(mt.itl_ms.p95, 3) if mt.itl_ms.count else None,
        "tpot_ms_mean": round(mt.tpot_ms.mean, 3) if mt.tpot_ms.count else None,
        "request_latency_ms_mean": round(mt.request_latency_ms.mean, 2),
        "error_rate": round(mt.error_rate, 4),
        "completed_requests": mt.completed_requests,
        "failed_requests": mt.failed_requests,
        "avg_power_watts": mt.avg_power_watts,
        "energy_joule": mt.energy_joule,
        "output_tokens_per_joule": mt.output_tokens_per_joule,
        "vram_used_gib_max": mt.vram_used_gib_max,
        "gpu_utilization_pct_mean": mt.gpu_utilization_pct_mean,
        "duration_s": round(m.duration_s, 2),
    }


def write_csv(rd, cells: list[MeasurementCell]) -> Path:
    import csv
    p = rd.path / "metrics.csv"
    rows = [_cell_row(m) for m in cells]
    if not rows:
        return p
    with open(p, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        for r in rows:
            w.writerow(r)
    return p


def write_metrics_json(rd, cells: list[MeasurementCell]) -> Path:
    p = rd.path / "metrics.json"
    payload = {
        "generator": REPORT_GENERATOR_VERSION,
        "cells": [_cell_row(m) for m in cells],
        "full": [m.metrics.model_dump(mode="json") for m in cells],
    }
    rd.atomic_write_json(p, payload)
    return p


def write_parquet(rd, cells: list[MeasurementCell]) -> Path | None:
    p = rd.path / "measurements.parquet"
    rows = [_cell_row(m) for m in cells]
    if not rows:
        return p
    try:
        import pandas as pd
        df = pd.DataFrame(rows)
        df.to_parquet(p, index=False)
        return p
    except Exception:
        # Fall back to pyarrow directly.
        try:
            import pyarrow as pa
            import pyarrow.parquet as pq
            pq.write_table(pa.Table.from_pylist(rows), p)
            return p
        except Exception:
            return None


# ---------------------------------------------------------------------------
# HTML dashboard (Plotly, inlined)
# ---------------------------------------------------------------------------
def build_html(
    manifest: RunManifest,
    kpis: SummaryKpis,
    cells: list[MeasurementCell],
) -> str:
    """Render a self-contained Plotly dashboard for the run."""
    import plotly.graph_objects as go
    import plotly.io

    fig = go.Figure()

    # Headline KPIs
    fig.update_layout(
        title=f"<b>llmbench</b> — {kpis.model or manifest.model} "
              f"({kpis.engine or manifest.engine}) on {kpis.gpu or 'GPU'}",
        template="plotly_dark",
        height=620,
    )

    valid = [m for m in cells if m.integrity.is_valid()]

    # Aggregate output TPS by concurrency (the scaling curve)
    conc_curve = {}
    for m in valid:
        if m.workload.load_mode.value == "closed_loop":
            conc_curve[m.workload.concurrency] = m.metrics.output_tps
    if conc_curve:
        xs = sorted(conc_curve)
        fig.add_trace(go.Scatter(
            x=xs, y=[conc_curve[x] for x in xs],
            mode="lines+markers",
            name="aggregate output tok/s vs concurrency",
            line=dict(color="#76B900", width=3),
        ))

    # TTFT (p95) by context (ISL) at concurrency 1
    ctx_ttft = {}
    for m in valid:
        if m.workload.concurrency == 1 and m.metrics.ttft_ms.count:
            ctx_ttft[m.workload.input_tokens] = m.metrics.ttft_ms.p95
    if ctx_ttft:
        xs = sorted(ctx_ttft)
        fig.add_trace(go.Scatter(
            x=xs, y=[ctx_ttft[x] for x in xs],
            mode="lines+markers",
            name="TTFT p95 (ms) vs context (tokens)",
            yaxis="y2",
            line=dict(color="#E0C72F", width=2),
        ))

    # ITL p95 by concurrency (if any)
    conc_itl = {}
    for m in valid:
        if m.workload.load_mode.value == "closed_loop" and m.metrics.itl_ms.count:
            conc_itl[m.workload.concurrency] = m.metrics.itl_ms.p95
    if conc_itl:
        xs = sorted(conc_itl)
        fig.add_trace(go.Scatter(
            x=xs, y=[conc_itl[x] for x in xs],
            mode="lines+markers",
            name="ITL p95 (ms) vs concurrency",
            yaxis="y2",
            line=dict(color="#5C6BC0", width=2),
        ))

    fig.update_layout(
        xaxis_title="concurrency",
        yaxis=dict(title="aggregate output tok/s"),
        yaxis2=dict(title="ms (p95)"),
        legend=dict(orientation="h", yanchor="top", y=-0.25),
        margin=dict(l=50, r=50, t=80, b=70),
    )

    kpi_html = _kpi_panel(kpis, manifest)
    table_html = _cell_table(valid or cells)
    html = f"""<!doctype html>
<html><head><meta charset="utf-8">
<title>llmbench — {kpis.model or manifest.model}</title>
<style>
:root {{ --nv:#76B900; --bg:#1E1E1E; --card:#262626; --txt:#F0F0F0; --muted:#9a9a9a; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--bg); color:var(--txt);
  font-family:'Segoe UI',system-ui,sans-serif; padding:24px; }}
h1 {{ color:var(--nv); font-weight:600; }}
.kpis {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr));
  gap:12px; margin-bottom:20px; }}
.kpi {{ background:var(--card); border-radius:10px; padding:14px;
  border-left:3px solid var(--nv); }}
.kpi .v {{ font-size:1.5rem; font-weight:700; color:var(--nv); }}
.kpi .l {{ color:var(--muted); font-size:.8rem; text-transform:uppercase;
  letter-spacing:.05em; }}
.card {{ background:var(--card); border-radius:10px; padding:16px;
  margin:16px 0; overflow-x:auto; }}
table {{ border-collapse:collapse; width:100%; font-size:.85rem; }}
th,td {{ padding:6px 10px; text-align:right; border-bottom:1px solid #333; }}
th:first-child,td:first-child {{ text-align:left; }}
th {{ color:var(--nv); }}
.badge {{ padding:2px 8px; border-radius:10px; font-size:.75rem; }}
.b-VALID {{ background:#1c3a1c; color:#7ddc7d; }}
.b-VALID_WITH_WARNINGS {{ background:#3a331c; color:#e0c72f; }}
.b-INVALID {{ background:#3a1c1c; color:#e06060; }}
#chart {{ width:100%; }}
</style>
<script src="https://cdn.plot.ly/plotly-2.35.0.min.js"></script>
</head>
<body>
<h1>llmbench — {kpis.model or manifest.model or '?'}</h1>
{kpis_panel_html(kpis, manifest)}
<div class="card"><div id="chart">{plotly.io.to_html(fig, full_html=False, include_plotlyjs=True)}</div></div>
<div class="card"><h3>Measurement cells</h3>{table_html}</div>
</body></html>"""
    return html


def kpis_panel_html(kpis, manifest) -> str:
    def kv(label, value):
        return f'<div class="kpi"><div class="v">{value}</div><div class="l">{label}</div></div>'
    def fmt(v, unit=""):
        if v is None:
            return "—"
        return f"{v}{unit}"
    panel = '<div class="kpis">'
    panel += kv("peak aggregate tok/s", fmt(_round(kpis.peak_aggregate_tps, 1)))
    panel += kv("peak decode tok/s (per user)", fmt(_round(kpis.peak_decode_tps, 1)))
    panel += kv("best TTFT p95 (ms)", fmt(_round(kpis.best_ttft_ms, 1)))
    panel += kv("max stable concurrency", kpis.max_stable_concurrency or "—")
    panel += kv("avg power (W)", fmt(_round(kpis.average_power_watts, 0)))
    panel += kv("tok/s per joule", fmt(_round(kpis.tokens_per_joule, 3)))
    panel += kv("peak VRAM (GiB)", fmt(_round(kpis.peak_vram_gib, 1)))
    panel += kv("integrity", kpis.integrity_state)
    panel += "</div>"
    return panel


def _kpi_panel(kpis, manifest) -> str:  # used inline (legacy helper)
    return kpis_panel_html(kpis, manifest)


def _cell_table(cells: list[MeasurementCell]) -> str:
    rows = []
    for m in cells:
        mt = m.metrics
        def f(v, nd=1):
            return "—" if v is None else f"{v:.{nd}f}"
        state_cls = m.integrity.state.value
        reasons = ";".join(m.integrity.reasons[:3])
        rows.append(
            "<tr>"
            f"<td>{m.workload.label()}</td>"
            f"<td>{mt.output_tps:.1f}</td>"
            f"<td>{f(mt.ttft_ms.p95 if mt.ttft_ms.count else None)}</td>"
            f"<td>{f(mt.itl_ms.p95 if mt.itl_ms.count else None)}</td>"
            f"<td>{mt.error_rate*100:.1f}%</td>"
            f"<td><span class='badge b-{state_cls}'>{state_cls}</span></td>"
            f"<td title='{reasons}'></td>"
            "</tr>"
        )
    return (
        "<table><thead><tr>"
        "<th>cell</th><th>out tok/s</th><th>TTFT p95 (ms)</th>"
        "<th>ITL p95 (ms)</th><th>err</th><th>integrity</th><th>reasons</th>"
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
    )


def _round(v, nd):
    return None if v is None else round(v, nd)


# ---------------------------------------------------------------------------
# Orchestration (called by the CLI)
# ---------------------------------------------------------------------------
def write_run_artifacts(rd, manifest: RunManifest, kpis: SummaryKpis,
                       cells: list[MeasurementCell]) -> dict:
    """Write summary.json, integrity.json, metrics.csv/json/parquet, index.html."""
    # summary.json
    rd.atomic_write_json(rd.path / "summary.json", {
        "manifest": manifest.model_dump(mode="json"),
        "kpis": kpis.model_dump(mode="json"),
        "cells": [_cell_row(m) for m in cells],
    })

    # integrity.json
    integ = {
        "run_state": kpis.integrity_state,
        "cells": [
            {"cell_id": m.cell_id, "state": m.integrity.state.value,
             "reasons": m.integrity.reasons, "notes": m.integrity.notes}
            for m in cells
        ],
    }
    rd.atomic_write_json(rd.path / "integrity.json", integ)

    # manifest.json
    rd.atomic_write_json(rd.path / "manifest.json",
                        manifest.model_dump(mode="json"))

    write_csv(rd, cells)
    write_metrics_json(rd, cells)
    write_parquet(rd, cells)

    # index.html (the Plotly dashboard)
    html = build_html(manifest, kpis, cells)
    rd.atomic_write_text(rd.path / "index.html", html)

    return {"artifacts": ["summary.json", "integrity.json", "manifest.json",
                          "metrics.csv", "metrics.json", "measurements.parquet",
                          "index.html"]}
