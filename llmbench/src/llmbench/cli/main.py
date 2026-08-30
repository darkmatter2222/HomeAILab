"""llmbench CLI (goal.md §36).

    llmbench run --target http://TARGET:PORT/v1 --mode light --budget 2h

The child runner: measure an already-running deployment, never restart it.
Writes a full run directory + (optionally) auto-updates the static site.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from ..schemas import (
    BENCHMARK_SUITE_VERSION,
    DeploymentConfig,
    RunManifest,
    SCORING_VERSION,
    REPORT_GENERATOR_VERSION,
    SummaryKpis,
    BenchmarkMode,
)
from ..security.sanitize import Sanitizer
from ..storage.run_dir import RunDirectory, slugify, configuration_id
from ..discovery.endpoint import EndpointProbe
from ..discovery.host import HostInspector
from ..planner.plan import (
    Budget,
    parse_budget,
    light_plan,
    heavy_plan,
    Planner,
)
from ..benchmark.executor import CellExecutor, ExecutorConfig
from ..adapters import get_adapter
from ..integrity.check import overall_state, reason_codes
from ..reports import report


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="llmbench",
        description="Single-GPU LLM inference benchmark (child runner).",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    run = sub.add_parser("run", help="run a benchmark against a target endpoint")
    run.add_argument("--target", required=True,
                     help="OpenAI-compatible base, e.g. http://host:8006/v1")
    run.add_argument("--model", default="auto",
                     help="model name (default: auto-discover)")
    run.add_argument("--mode", default="light", choices=["light", "heavy"],
                     help="budget policy (default light)")
    run.add_argument("--budget", default="2h",
                     help="time budget: '2h', '45m', '300s' (default 2h)")
    run.add_argument("--api-key", default=None,
                     help="bearer token (env LLMBENCH_API_KEY also read)")
    run.add_argument("--out", default="benchmarks",
                     help="output root (default ./benchmarks)")
    run.add_argument("--label", default=None, help="configuration label")
    run.add_argument("--max-context", type=int, default=None,
                     help="override detected max context (tokens)")
    run.add_argument("--max-concurrency", type=int, default=None,
                     help="cap concurrency (default: engine max_num_seqs or 16)")
    run.add_argument("--no-gpu", action="store_true",
                     help="skip GPU telemetry (e.g. when GPU is on a remote host)")
    run.add_argument("--ssh-gpu", default=None,
                     help="SSH host/alias for remote GPU nvidia-smi (DGX Spark, etc.)")
    run.add_argument("--samples", type=int, default=8,
                     help="closed-loop samples per cell (default 8)")
    run.add_argument("--metrics-url", default=None,
                     help="engine /metrics endpoint for cross-validation")
    run.add_argument("--skip-site", action="store_true",
                     help="do not regenerate the static site")
    run.add_argument("--site-out", default="site",
                     help="static site output dir (default ./site)")
    run.add_argument("--seed", type=int, default=20260823,
                     help="RNG seed for synthetic prompts")
    run.add_argument("-q", "--quiet", action="store_true")
    return p


async def _discover(args) -> tuple:
    """Discover endpoint metadata + detect the engine adapter."""
    probe = EndpointProbe(
        base_url=args.target,
        model=args.model,
        api_key=args.api_key or os.environ.get("LLMBENCH_API_KEY"),
        metrics_url=args.metrics_url,
    )
    meta = await probe.discover()
    engine_name, adapter = probe.detect_engine(meta)
    return probe, meta, engine_name, adapter


def _host_config(args, meta) -> dict:
    return {
        "out": args.out,
        "label": args.label,
        "config_id": None,
    }


async def cmd_run(args) -> int:
    quiet = args.quiet
    def log(*a):
        if not quiet:
            print(*a)

    api_key = args.api_key or os.environ.get("LLMBENCH_API_KEY")
    log(f"==> discovering target {args.target}")
    probe, meta, engine_name, adapter = await _discover(args)
    log(f"    engine={engine_name} model={meta.model!r} "
        f"max_len={meta.model_max_len} version={meta.version}")

    # Host + GPU introspection (goal.md §8, §21).  When the GPU is on a
    # remote host (--ssh-gpu), inspect there so hardware + GPU are the
    # actual deployment host, not the client.
    log("==> host + GPU introspection")
    from ..discovery.host import HostConfig
    hcfg = HostConfig(
        mode="ssh" if args.ssh_gpu else "local",
        ssh_host=args.ssh_gpu,
    )
    host = HostInspector(hcfg).inspect()
    gpus = host.gpus
    gpu_line = "; ".join(g.name or f"gpu[{i}]" for i, g in enumerate(gpus))
    log(f"    OS={host.os.os} {host.os.distribution} arch={host.os.arch}")
    if gpus:
        log(f"    GPU={gpu_line}")
    else:
        log("    GPU=nvidia-smi not found (telemetry will be limited)")
    if host.multi_gpu_warning:
        log(f"    WARNING: {host.multi_gpu_warning}")

    # Deployment config (normalized via the adapter, goal.md §9)
    cfg = DeploymentConfig(engine=engine_name, model=meta.model)
    cfg.engine_version = meta.version
    cfg.engine_image = meta.image
    if meta.model_max_len is not None:
        cfg.max_model_len = meta.model_max_len
    # Attempt to normalize the full config from process cmdline / env when
    # we're co-located with the server (best effort; the child never modifies).
    try:
        from ..discovery.processes import find_serving_process, read_cmdline, read_env
        pid = find_serving_process()
        if pid is not None:
            cmdline = read_cmdline(pid)
            env = read_env(pid)
            if cmdline:
                cfg = adapter.normalize_config(cmdline, env, meta.as_dict())
                cfg.engine = engine_name
                cfg.model = meta.model or cfg.model
                cfg.engine_version = meta.version
                log(f"    normalized config from pid {pid}")
    except Exception as e:
        log(f"    (config normalization skipped: {e})")

    # Budget + plan (goal.md §25, §26)
    mode = BenchmarkMode(args.mode)
    budget = Budget(mode=mode, total_seconds=parse_budget(args.budget))
    max_ctx = args.max_context or meta.model_max_len
    plan = (
        light_plan(max_ctx, budget, max_concurrency=args.max_concurrency)
        if mode == BenchmarkMode.LIGHT
        else heavy_plan(max_ctx, budget, max_concurrency=args.max_concurrency)
    )
    log(f"==> mode={args.mode} budget={args.budget} planned {len(plan)} cells")

    # Run directory
    cfg_slug = slugify(meta.model or "model")
    config_id = configuration_id(cfg, cfg_slug)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    rd = RunDirectory(
        output_root=args.out,
        model_slug=cfg_slug,
        config_id=config_id,
        run_id=run_id,
    )
    log(f"    run dir: {rd.path}")

    # Sanitizer (secrets out before disk writes, goal.md §10).  The first
    # real host/IP seen is aliased gpu-host-01 by alias_for_host(); pin it
    # here so the deployment host is always the first alias.
    sanitizer = Sanitizer()
    if args.ssh_gpu:
        sanitizer.register_host(args.ssh_gpu.lower(), "gpu-host-01")
    host_addr = args.target.split("//", 1)[1].split("/", 1)[0]
    if host_addr not in ("localhost", "127.0.0.1"):
        sanitizer.alias_for_host(host_addr)

    # Write the run-level artifacts that don't depend on cell results.
    cfg_sans = cfg.model_dump()
    cfg_sans.pop("env_vars", None)
    rd.atomic_write_json(rd.path / "configuration.json", cfg_sans)
    rd.atomic_write_json(rd.path / "hardware.json", host.model_dump(mode="json"))

    # Executor
    exec_cfg = ExecutorConfig(
        endpoint=args.target,
        model=meta.model or cfg.model,
        api_key=api_key,
        is_chat=adapter.is_chat_completions_supported(),
        ignore_eos=adapter.ignore_eos_supported(),
        min_tokens=0 if not adapter.min_tokens_supported() else 1,
        gpu_telemetry=not args.no_gpu,
        gpu_ssh_host=args.ssh_gpu,
        gpu_index=0,
        sample_interval_s=1.0,
        metrics_url=args.metrics_url or probe.metrics_url,
        adapter=adapter,
        run_dir=rd,
        sanitizer=sanitizer,
        samples_per_cell=args.samples,
    )
    executor = CellExecutor(exec_cfg)

    planner = Planner(
        plan=plan,
        budget=budget,
        max_concurrency=args.max_concurrency,
        max_context=max_ctx,
    )
    # Seed the plan into the planner (it only returns pending cells).
    pending = list(plan)
    t_start = time.time()
    completed_cells = 0
    results = []

    log(f"==> running benchmark (max {budget.total_seconds/3600:.2f} h)")
    while True:
        if planner.budget_exhausted(time.time() - t_start):
            log("    budget exhausted, stopping")
            break
        cell = planner.next_cell()
        if cell is None:
            break
        cell.cell_id = f"c{completed_cells:03d}"
        log(f"    [{completed_cells+1}] {cell.label()}")
        try:
            mc = await executor.run_cell(cell)
        except Exception as e:
            log(f"        ! cell failed: {e}")
            rd.append_planner({"event": "cell_error", "cell": cell.label(), "error": str(e)})
            completed_cells += 1
            continue
        planner.mark_done(cell, mc)
        results.append(mc)
        rd.write_state({
            "run_id": run_id,
            "completed": [c.cell_id for c in results],
            "total_planned": len(plan),
            "updated_at": _now_iso(),
        })
        rd.append_planner({"event": "cell_done", "cell": cell.label(),
                           "state": mc.integrity.state.value,
                           "output_tps": round(mc.metrics.output_tps, 2),
                           "duration_s": round(mc.duration_s, 1)})
        # Adaptive refinement (only while we still have budget).
        for new_cell in planner.refine():
            rd.append_planner({"event": "refine", "cell": new_cell.label()})
        completed_cells += 1

    # Finalize: manifest + summary + run_result + integrity + CSV/JSON/parquet.
    final_state = overall_state([m.integrity for m in results])
    manifest = _build_manifest(
        args, rd, cfg, host, meta, mode, budget, results, final_state,
    )
    kpis = _build_kpis(cfg, host, results, final_state)
    report.write_run_artifacts(rd, manifest, kpis, results)

    # run_result.json (the Definition-of-Done artifact, goal.md §38)
    run_result = {
        "run_id": run_id,
        "configuration_id": config_id,
        "engine": engine_name,
        "model": meta.model,
        "integrity_state": final_state,
        "cells": [
            {"cell_id": m.cell_id, "label": m.workload.label(),
             "state": m.integrity.state.value,
             "output_tps": round(m.metrics.output_tps, 2)}
            for m in results
        ],
        "summary": kpis.model_dump(mode="json"),
        "run_dir": str(rd.path),
        "completed_at": _now_iso(),
    }
    rd.atomic_write_json(rd.path / "run_result.json", run_result)
    rd.write_state({
        "run_id": run_id,
        "completed": [c.cell_id for c in results],
        "total_planned": len(plan),
        "finished": True,
        "updated_at": _now_iso(),
    })

    log(f"==> done: {completed_cells} cells, state={final_state}")
    log(f"    run_result: {rd.path / 'run_result.json'}")
    log(f"    report: {rd.path / 'index.html'}")

    # Auto-update the static site (goal.md §33) unless skipped.
    if not args.skip_site:
        from ..site import build_site
        site_dir = Path(args.site_out)
        try:
            build_site(args.out, site_dir)
            log(f"    site regenerated at {site_dir}")
        except Exception as e:
            log(f"    (site generation skipped: {e})")

    return 0


def _build_manifest(args, rd, cfg, host, meta, mode, budget, results, final_state) -> RunManifest:
    kpis = _build_kpis(cfg, host, results, final_state)
    m = RunManifest(
        schema_version="1.0.0",
        benchmark_suite_version=BENCHMARK_SUITE_VERSION,
        scoring_version=SCORING_VERSION,
        report_generator_version=REPORT_GENERATOR_VERSION,
        run_id=rd.path.name,
        configuration_id=rd.path.parent.name,
        run_label=args.label,
        configuration_label=args.label,
        model=cfg.model or meta.model,
        engine=cfg.engine,
        engine_version=cfg.engine_version,
        deployment=cfg,
        hardware=host,
        python_version=sys.version.split()[0],
        random_seed=args.seed,
        mode=mode,
        budget_s=budget.total_seconds,
        telemetry_sources=(["nvidia-smi"] if (not args.no_gpu or args.ssh_gpu) else []),
        server_metrics_sources=([args.metrics_url or "engine /metrics"] if args.metrics_url else []),
        integrity_state=final_state,
        integrity_reasons=reason_codes([r.integrity for r in results]),
        tags=[],
    )
    m.started_at = host.collected_at
    return m


def _build_kpis(cfg, host, results, final_state) -> SummaryKpis:
    k = SummaryKpis(integrity_state=final_state)
    k.model = cfg.model
    k.engine = cfg.engine
    k.engine_version = cfg.engine_version
    k.quantization = cfg.quantization
    k.max_context = cfg.max_model_len
    if host.gpus and host.gpus[0].name:
        k.gpu = host.gpus[0].name

    valid = [m for m in results if m.integrity.is_valid()]
    pool = valid or results
    if pool:
        k.peak_aggregate_tps = max((m.metrics.output_tps for m in pool), default=None)
        k.peak_decode_tps = max(
            (m.metrics.output_tps_per_user for m in pool if m.metrics.output_tps_per_user),
            default=None,
        )
        ttfts = [m.metrics.ttft_ms.p95 for m in pool if m.metrics.ttft_ms.count]
        if ttfts:
            k.best_ttft_ms = min(ttfts)
        # max stable concurrency: highest concurrency with a valid cell.
        k.max_stable_concurrency = max(
            (m.workload.concurrency for m in pool if m.workload.load_mode.value == "closed_loop"),
            default=None,
        )
        # Power / efficiency from any cell with GPU data.
        powered = [m for m in pool if m.metrics.energy_joule]
        if powered:
            k.average_power_watts = round(
                sum(m.metrics.avg_power_watts or 0 for m in powered) / len(powered), 2
            )
            best_eff = max(powered, key=lambda m: m.metrics.output_tokens_per_joule or 0)
            if best_eff.metrics.output_tokens_per_joule:
                k.tokens_per_joule = round(best_eff.metrics.output_tokens_per_joule, 3)
        # peak vram
        vram = [m.metrics.vram_used_gib_max for m in pool
                if m.metrics.vram_used_gib_max is not None]
        if vram:
            k.peak_vram_gib = max(vram)
    return k


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.cmd == "run":
        return asyncio.run(cmd_run(args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
