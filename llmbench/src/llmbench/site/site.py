"""Static site generation (goal.md §33).

Scans the benchmarks/ tree for completed runs and renders a static HTML site:
* ``index.html``           - catalog: one card per (model, configuration) with
                             its best headline numbers + links to every run.
* ``models/<model-slug>.html`` - per-model tuning history: chronological list of
                             every configuration change with before/after KPI
                             deltas (the "how did this model's tuning evolve"
                             page).

The site is plain HTML (no build step, no JS framework) so it can be served
from any static host.  It reads only the sanitized run artifacts.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class RunRecord:
    model_slug: str
    config_id: str
    run_id: str
    path: Path
    engine: str = ""
    quantization: str = ""
    max_context: int | None = None
    integrity_state: str = ""
    peak_aggregate_tps: float | None = None
    best_ttft_ms: float | None = None
    peak_decode_tps: float | None = None
    max_stable_concurrency: int | None = None
    tokens_per_joule: float | None = None
    peak_vram_gib: float | None = None
    completed_at: str = ""
    n_cells: int = 0


def _load_run(path: Path) -> RunRecord | None:
    rr = RunRecord(
        model_slug=path.parts[-4],
        config_id=path.parts[-2],
        run_id=path.name,
        path=path,
    )
    rr_run_result = path / "run_result.json"
    if rr_run_result.exists():
        try:
            data = json.loads(rr_run_result.read_text(encoding="utf-8"))
            rr.engine = data.get("engine", "")
            rr.integrity_state = data.get("integrity_state", "")
            rr.completed_at = data.get("completed_at", "")
            summary = data.get("summary", {})
            rr.peak_aggregate_tps = summary.get("peak_aggregate_tps")
            rr.best_ttft_ms = summary.get("best_ttft_ms")
            rr.peak_decode_tps = summary.get("peak_decode_tps")
            rr.max_stable_concurrency = summary.get("max_stable_concurrency")
            rr.tokens_per_joule = summary.get("tokens_per_joule")
            rr.peak_vram_gib = summary.get("peak_vram_gib")
            rr.n_cells = len(data.get("cells", []))
        except Exception:
            pass
    cfg = path / "configuration.json"
    if cfg.exists():
        try:
            c = json.loads(cfg.read_text(encoding="utf-8"))
            rr.quantization = c.get("quantization") or ""
            rr.max_context = c.get("max_model_len")
            rr.engine = rr.engine or c.get("engine", "")
        except Exception:
            pass
    return rr


def scan_runs(benchmarks_root: str | Path) -> list[RunRecord]:
    """Find every run directory (one level: model/day/config/run)."""
    root = Path(benchmarks_root)
    out: list[RunRecord] = []
    if not root.exists():
        return out
    for model_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        for day_dir in sorted(p for p in model_dir.iterdir() if p.is_dir()):
            for cfg_dir in sorted(p for p in day_dir.iterdir() if p.is_dir()):
                for run_dir in sorted(p for p in cfg_dir.iterdir() if p.is_dir()):
                    rec = _load_run(run_dir)
                    if rec is not None:
                        out.append(rec)
    return out


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------
_CSS = """
:root{--nv:#76B900;--bg:#1E1E1E;--card:#262626;--txt:#F0F0F0;--muted:#9a9a9a;--line:#333}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--txt);
 font-family:'Segoe UI',system-ui,sans-serif;padding:28px;max-width:1100px;margin:0 auto}
h1{color:var(--nv);font-weight:600}
h2{color:var(--nv);border-bottom:1px solid var(--line);padding-bottom:6px}
a{color:var(--nv);text-decoration:none}a:hover{text-decoration:underline}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:14px}
.card{background:var(--card);border-radius:10px;padding:16px;border-left:3px solid var(--nv)}
.card h3{margin:0 0 8px;font-size:1rem}
.meta{color:var(--muted);font-size:.8rem;line-height:1.5}
.kpi{font-size:1.3rem;font-weight:700;color:var(--nv)}
.kpi .l{font-size:.7rem;color:var(--muted);text-transform:uppercase;letter-spacing:.05em}
.badge{padding:2px 8px;border-radius:10px;font-size:.75rem}
.b-VALID{background:#1c3a1c;color:#7ddc7d}
.b-VALID_WITH_WARNINGS{background:#3a331c;color:#e0c72f}
.b-INVALID{background:#3a1c1c;color:#e06060}
.hist{list-style:none;padding:0}
.hist li{background:var(--card);border-radius:10px;padding:14px;margin:10px 0}
.hist li .t{font-size:.8rem;color:var(--muted)}
.hist li .d{font-size:.9rem;margin-top:6px}
.up{color:#7ddc7d}.down{color:#e06060}.flat{color:var(--muted)}
table{border-collapse:collapse;width:100%}th,td{padding:6px 10px;text-align:right;
 border-bottom:1px solid var(--line)}th:first-child,td:first-child{text-align:left}
th{color:var(--nv)}
"""


def _page(title: str, body: str) -> str:
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>{title}</title><style>{_CSS}</style></head>"
        f"<body><h1>llmbench</h1>{body}</body></html>"
    )


def _fmt(v, nd=1, unit=""):
    if v is None:
        return "—"
    return f"{v:.{nd}f}{unit}"


def _best_for_config(runs: list[RunRecord], config_id: str) -> RunRecord:
    """Best (highest peak aggregate tps) run for a given configuration."""
    cfg_runs = [r for r in runs if r.config_id == config_id]
    return max(cfg_runs, key=lambda r: (r.peak_aggregate_tps or 0))


def build_site(
    benchmarks_root: str | Path,
    out_dir: str | Path,
) -> Path:
    """Render the catalog + per-model history pages.  Returns the site dir."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    runs = scan_runs(benchmarks_root)

    # Group by model
    by_model: dict[str, list[RunRecord]] = {}
    for r in runs:
        by_model.setdefault(r.model_slug, []).append(r)

    # ---- index.html (catalog) ----
    cards = []
    for model_slug in sorted(by_model):
        model_runs = by_model[model_slug]
        # Distinct configurations for this model.
        cfg_ids = sorted({r.config_id for r in model_runs})
        for cid in cfg_ids:
            best = _best_for_config(model_runs, cid)
            n_runs = sum(1 for r in model_runs if r.config_id == cid)
            cards.append(
                f"""<div class="card">
  <h3>{model_slug} <span class="meta">({best.engine or 'unknown'})</span></h3>
  <div class="kpi">{_fmt(best.peak_aggregate_tps)} <span class="l">peak tok/s</span></div>
  <div class="meta" style="margin-top:8px">
    quant: {best.quantization or '—'} · max ctx: {best.max_context or '—'}<br>
    TTFT p95: {_fmt(best.best_ttft_ms, 1, ' ms')} ·
    stable conc: {best.max_stable_concurrency or '—'}<br>
    VRAM: {_fmt(best.peak_vram_gib)} · tok/J: {_fmt(best.tokens_per_joule, 2)}<br>
    {n_runs} run(s) · <span class="badge b-{best.integrity_state or 'VALID'}">
      {best.integrity_state or 'VALID'}</span>
  </div>
  <div class="meta" style="margin-top:8px">
    <a href="models/{model_slug}.html">tuning history →</a>
  </div>
</div>"""
            )
    idx_body = (
        '<h2>Configuration catalog</h2>'
        + ("".join(cards) if cards else '<p class="meta">no runs found</p>')
    )
    (out / "index.html").write_text(_page("llmbench — catalog", idx_body), encoding="utf-8")

    # ---- models/<model>.html (tuning history) ----
    for model_slug, model_runs in by_model.items():
        # Order configurations chronologically by their earliest completed_at,
        # then show each configuration's best run with before/after deltas vs
        # the previous configuration (the "tuning history").
        cfg_order = []
        seen = set()
        for r in sorted(model_runs, key=lambda r: r.completed_at or ""):
            if r.config_id not in seen:
                cfg_order.append(r.config_id)
                seen.add(r.config_id)

        hist_items = []
        prev: RunRecord | None = None
        for cid in cfg_order:
            best = _best_for_config(model_runs, cid)
            delta_html = ""
            if prev is not None:
                delta_html = _delta_row(best, prev)
            hist_items.append(
                f"""<li>
  <div class="t">{best.completed_at or 'unknown date'} · {cid} · {best.engine}</div>
  <div class="d">
    peak <b>{_fmt(best.peak_aggregate_tps)}</b> tok/s ·
    TTFT p95 {_fmt(best.best_ttft_ms, 1, ' ms')} ·
    stable conc {best.max_stable_concurrency or '—'} ·
    VRAM {_fmt(best.peak_vram_gib)} GiB ·
    <span class="badge b-{best.integrity_state or 'VALID'}">{best.integrity_state or 'VALID'}</span>
  </div>
  {delta_html}
</li>"""
            )
            prev = best

        hist_body = (
            f'<p class="meta"><a href="../index.html">← catalog</a></p>'
            f'<h2>{model_slug} — tuning history</h2>'
            f'<ul class="hist">{"".join(hist_items) or "<li class=\"meta\">no runs</li>"}</ul>'
        )
        (out / "models").mkdir(exist_ok=True)
        (out / "models" / f"{model_slug}.html").write_text(
            _page(f"llmbench — {model_slug}", hist_body), encoding="utf-8"
        )

    return out


def _delta_row(curr: RunRecord, prev: RunRecord) -> str:
    """Render before/after KPI deltas between two consecutive configs."""
    def delta(kind, unit=""):
        c, p = getattr(curr, kind), getattr(prev, kind)
        if c is None or p is None or p == 0:
            return f'<span class="flat">{kind}: —</span>'
        pct = (c - p) / p * 100
        cls = "up" if pct >= 0 else "down"
        arrow = "▲" if pct >= 0 else "▼"
        return (f'<span class="{cls}">{kind} {arrow} {pct:+.0f}% '
                f'({p:.1f}{unit} → {c:.1f}{unit})</span>')
    parts = [
        delta("peak_aggregate_tps"),
        delta("best_ttft_ms", "ms"),  # lower is better
    ]
    return f'<div class="d" style="margin-top:4px">{" · ".join(parts)}</div>'
