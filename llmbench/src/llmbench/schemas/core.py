"""Core Pydantic models for llmbench measurement data.

All values use canonical units (goal.md §28):
milliseconds, seconds, tokens/sec, requests/sec, bytes, MiB/GiB, watts,
joules, degrees Celsius.  Ambiguous unit names are avoided.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from . import (
    BENCHMARK_SUITE_VERSION,
    MEASUREMENT_SCHEMA_VERSION,
    VALID,
    REPORT_GENERATOR_VERSION,
    SCORING_VERSION,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ModelConfig(BaseModel):
    """Common Pydantic configuration for all llmbench models."""

    model_config = ConfigDict(
        extra="ignore",
        use_enum_values=False,
    )


# ---------------------------------------------------------------------------
# Enums (goal.md §11, §16, §17)
# ---------------------------------------------------------------------------
class BenchmarkMode(str, Enum):
    LIGHT = "light"
    HEAVY = "heavy"


class CacheMode(str, Enum):
    COLD = "cold"
    WARM = "warm"


class LoadMode(str, Enum):
    CLOSED_LOOP = "closed_loop"
    OPEN_LOOP_CONSTANT = "open_loop_constant"
    OPEN_LOOP_POISSON = "open_loop_poisson"


class IntegrityState(str, Enum):
    VALID = "VALID"
    VALID_WITH_WARNINGS = "VALID_WITH_WARNINGS"
    INVALID = "INVALID"


# ---------------------------------------------------------------------------
# Workload coordinates (goal.md §11)
# ---------------------------------------------------------------------------
class WorkloadCell(BaseModel):
    """A single benchmark measurement cell (the multidimensional coordinate)."""

    cell_id: str = ""
    input_tokens: int = 0          # target input context (ISL)
    target_output_tokens: int = 0  # target output length (OSL)
    concurrency: int = 1
    cache_mode: CacheMode = CacheMode.COLD
    load_mode: LoadMode = LoadMode.CLOSED_LOOP
    repetitions: int = 1
    arrival_rate: Optional[float] = None  # requests/sec for open-loop

    def label(self) -> str:
        return (
            f"ISL={self.input_tokens} OSL={self.target_output_tokens} "
            f"c={self.concurrency} cache={self.cache_mode} "
            f"load={self.load_mode}"
        )

    def key(self) -> tuple:
        return (
            self.input_tokens,
            self.target_output_tokens,
            self.concurrency,
            self.cache_mode,
            self.load_mode,
            self.arrival_rate or 0,
        )


# ---------------------------------------------------------------------------
# Statistical distributions (goal.md §18)
# ---------------------------------------------------------------------------
class MetricDistribution(BaseModel):
    """Statistical summary of a measured quantity.

    Units are documented per-metric in CellMetrics fields; this model
    itself is unit-agnostic.  p999 is only populated when the sample size
    supports it; `sample_n` always records the actual count so readers can
    judge percentile meaning.
    """

    count: int = 0
    mean: float = 0.0
    median: float = 0.0
    stddev: float = 0.0
    cv: Optional[float] = None      # coefficient of variation (stddev/mean)
    min: float = 0.0
    max: float = 0.0
    p50: float = 0.0
    p75: float = 0.0
    p90: float = 0.0
    p95: float = 0.0
    p99: float = 0.0
    p999: Optional[float] = None
    confidence_interval_95: Optional[list[float]] = None  # [lo, hi] for mean

    def limit_note(self) -> str:
        """Human-readable caveat about percentile reliability (§18)."""
        if self.count < 30:
            return (
                f"small sample (n={self.count}); percentiles are approximate"
            )
        return ""


def compute_distribution(values: list[float]) -> MetricDistribution:
    """Compute the canonical statistical summary for a value series."""
    if not values:
        return MetricDistribution()
    vals = sorted(values)
    n = len(vals)
    mean = sum(vals) / n
    if n > 1:
        var = sum((v - mean) ** 2 for v in vals) / (n - 1)
        stddev = var**0.5
    else:
        stddev = 0.0

    def pct(p: float) -> float:
        # Linear interpolation percentile (same as numpy 'linear').
        if n == 1:
            return vals[0]
        k = (n - 1) * p
        f = int(k)
        c = min(f + 1, n - 1)
        if f == c:
            return vals[f]
        return vals[f] + (vals[c] - vals[f]) * (k - f)

    ci95 = None
    if n >= 3 and stddev > 0:
        # 95% CI on the mean (t-approx; use 1.96 for n>=30 else conservative)
        se = stddev / n**0.5
        ci95 = [mean - 1.96 * se, mean + 1.96 * se]

    return MetricDistribution(
        count=n,
        mean=mean,
        median=pct(0.50),
        stddev=stddev,
        cv=(stddev / mean) if mean > 0 else None,
        min=vals[0],
        max=vals[-1],
        p50=pct(0.50),
        p75=pct(0.75),
        p90=pct(0.90),
        p95=pct(0.95),
        p99=pct(0.99),
        p999=pct(0.999) if n >= 100 else None,
        confidence_interval_95=ci95,
    )


# ---------------------------------------------------------------------------
# Network calibration (goal.md §19)
# ---------------------------------------------------------------------------
class NetworkStats(BaseModel):
    """Client-observed network effect of the benchmark link.

    Network-adjusted values never replace observed values; both are stored.
    """

    connection_time_s: Optional[float] = None   # TCP connect
    dns_time_s: Optional[float] = None          # DNS resolution (when applicable)
    tcp_rtt_ms: Optional[float] = None          # RTT estimate
    http_send_time_ms: Optional[float] = None
    http_wait_time_ms: Optional[float] = None
    http_receive_time_ms: Optional[float] = None
    connection_reuse: Optional[bool] = None
    bytes_sent: int = 0
    bytes_received: int = 0
    # Calibration result: estimated per-token network contribution.
    network_contribution_ms_per_token: Optional[float] = None


# ---------------------------------------------------------------------------
# Cross-source validation (goal.md §47)
# ---------------------------------------------------------------------------
class Discrepancy(BaseModel):
    """A measured disagreement between metric sources (client vs engine)."""

    metric: str
    client_value: float
    engine_value: float
    engine_source: str  # e.g. "vllm.time_to_first_token_seconds"
    relative_error_pct: float = 0.0
    material: bool = False  # True when beyond threshold


# ---------------------------------------------------------------------------
# Per-request raw measurements (goal.md §18, §41)
# ---------------------------------------------------------------------------
class RawRequest(BaseModel):
    """Timing for a single completed (or failed) request within a cell."""

    request_id: str
    ok: bool = True
    http_status: int = 200
    error_kind: Optional[str] = None  # timeout, malformed_stream, context_overflow...

    # Latency (seconds)
    request_latency_s: float = 0.0       # end-to-end
    time_to_first_byte_s: Optional[float] = None
    ttft_s: Optional[float] = None       # time to first *token*
    ttst_s: Optional[float] = None       # time to second token
    decode_duration_s: Optional[float] = None
    prefill_duration_s: Optional[float] = None  # derivable = ttft - ttfb
    inter_token_latencies_ms: list[float] = Field(default_factory=list)

    # Throughput (tokens/sec)
    decode_tps: Optional[float] = None
    prefill_tps: Optional[float] = None
    total_tps: Optional[float] = None

    # Sequences (tokens)
    input_tokens: int = 0                # actual, from usage when available
    output_tokens: int = 0               # actual
    total_tokens: int = 0
    target_output_tokens: int = 0
    finish_reason: Optional[str] = None
    eos_seen: Optional[bool] = None
    truncated: Optional[bool] = None

    # Stream integrity
    completed_stream: bool = True
    first_chunk_offset_s: Optional[float] = None

    @property
    def tpot_ms(self) -> Optional[float]:
        """Time per output token (mean ITL, ms) — goal.md §18."""
        if self.inter_token_latencies_ms:
            return sum(self.inter_token_latencies_ms) / len(
                self.inter_token_latencies_ms
            )
        return None

    @property
    def itl_distribution(self) -> MetricDistribution:
        return compute_distribution(self.inter_token_latencies_ms)


# ---------------------------------------------------------------------------
# Measurement cell results (goal.md §11, §28)
# ---------------------------------------------------------------------------
class CellMetrics(BaseModel):
    """Aggregated metrics for one measurement cell.

    Distributions are in the units named in the field:
    *_ms fields are milliseconds, *_s are seconds, *_tps are tokens/sec,
    *_rps are requests/sec, *_watts are watts, *_joule are joules.
    """

    # Latency (ms)
    ttft_ms: MetricDistribution
    ttst_ms: MetricDistribution
    itl_ms: MetricDistribution
    tpot_ms: MetricDistribution
    request_latency_ms: MetricDistribution
    prefill_duration_ms: MetricDistribution

    # Throughput
    output_tps: float = 0.0             # aggregate output tokens/sec (all streams)
    request_rps: float = 0.0           # completed requests/sec
    prompt_tokens_per_s: float = 0.0
    decode_tokens_per_s: float = 0.0
    total_tokens_per_s: float = 0.0
    output_tps_per_user: float = 0.0   # per-stream decode rate
    goodput_tps: Optional[float] = None
    goodput_slo: Optional[str] = None  # e.g. "ttft_ms<=500"

    # Sequence data
    actual_input_tokens_mean: float = 0.0
    actual_output_tokens_mean: float = 0.0
    total_tokens_mean: float = 0.0

    # Errors
    error_rate: float = 0.0            # fraction of failed requests
    http_error_rate: float = 0.0
    timeout_rate: float = 0.0
    malformed_stream_rate: float = 0.0
    incomplete_stream_rate: float = 0.0
    context_overflow_rate: float = 0.0
    cancelled_rate: float = 0.0
    truncated_rate: float = 0.0
    completed_requests: int = 0
    failed_requests: int = 0

    # Network (goal.md §19)
    network: NetworkStats = Field(default_factory=NetworkStats)
    network_adjusted_ttft_ms: Optional[MetricDistribution] = None

    # Efficiency (goal.md §22)
    avg_power_watts: Optional[float] = None
    peak_power_watts: Optional[float] = None
    energy_joule: Optional[float] = None
    output_tokens_per_joule: Optional[float] = None
    total_tokens_per_joule: Optional[float] = None
    joules_per_output_token: Optional[float] = None
    joules_per_request: Optional[float] = None
    output_tps_per_watt: Optional[float] = None
    requests_per_watt: Optional[float] = None

    # Cross-source validation (goal.md §47)
    discrepancies: list[Discrepancy] = Field(default_factory=list)

    # GPU snapshot for this cell
    gpu_utilization_pct_mean: Optional[float] = None
    gpu_utilization_pct_max: Optional[float] = None
    vram_used_gib_max: Optional[float] = None
    gpu_temp_c_mean: Optional[float] = None
    gpu_temp_c_max: Optional[float] = None
    sm_clock_mhz_mean: Optional[float] = None
    sm_clock_mhz_max: Optional[float] = None
    mem_clock_mhz_mean: Optional[float] = None
    throttle_events: int = 0


# ---------------------------------------------------------------------------
class IntegrityResult(BaseModel):
    """Integrity verdict for a cell (goal.md §23)."""

    state: IntegrityState = IntegrityState.VALID
    reasons: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    measured_at: datetime = Field(default_factory=utc_now)

    def is_valid(self) -> bool:
        return self.state in (
            IntegrityState.VALID,
            IntegrityState.VALID_WITH_WARNINGS,
        )


class MeasurementSource(BaseModel):
    """Provenance for a metric value (goal.md §3)."""

    name: str
    origin: str  # "client-observed" | "engine" | "gpu-telemetry" | "aiperf"
    endpoint: Optional[str] = None


# ---------------------------------------------------------------------------
class MeasurementCell(BaseModel):
    """A completed benchmark cell: workload coordinate + results + integrity."""

    cell_id: str
    workload: WorkloadCell
    started_at: datetime
    finished_at: datetime
    duration_s: float = 0.0
    metrics: CellMetrics
    integrity: IntegrityResult
    sources: list[MeasurementSource] = Field(default_factory=list)
    raw_requests: list[RawRequest] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Hardware / host (goal.md §8, §21)
# ---------------------------------------------------------------------------
class GpuInfo(BaseModel):
    name: str = ""
    architecture: str = ""
    memory_gib: Optional[float] = None
    memory_type: Optional[str] = None
    driver_version: Optional[str] = None
    cuda_version: Optional[str] = None
    compute_capability: Optional[str] = None
    pcie_generation: Optional[int] = None
    pcie_width: Optional[int] = None
    pcie_link_gen_current: Optional[int] = None
    pcie_link_width_current: Optional[int] = None
    sm_clock_mhz_max: Optional[float] = None
    mem_clock_mhz_max: Optional[float] = None
    power_limit_watts: Optional[float] = None
    default_power_limit_watts: Optional[float] = None
    temp_limit_c: Optional[float] = None
    ecc_enabled: Optional[bool] = None
    persistence_mode: Optional[bool] = None
    mig_mode: Optional[str] = None
    nvidia_smi_available: bool = False
    dcgm_available: bool = False
    nvml_available: bool = False
    extra: dict[str, Any] = Field(default_factory=dict)


class OSInfo(BaseModel):
    hostname_alias: str = "gpu-host-01"  # redacted public name (§10)
    os: str = ""
    distribution: str = ""
    kernel: str = ""
    arch: str = ""
    uptime_s: Optional[float] = None
    cpu_model: str = ""
    cpu_physical_cores: Optional[int] = None
    cpu_logical_cores: Optional[int] = None
    ram_gib: Optional[float] = None
    swap_gib: Optional[float] = None
    numa_nodes: Optional[int] = None
    pci_topology: Optional[str] = None


class HardwareInfo(BaseModel):
    os: OSInfo
    gpus: list[GpuInfo] = Field(default_factory=list)
    multi_gpu_warning: Optional[str] = None  # set when >1 active GPU (§6)
    collected_at: datetime = Field(default_factory=utc_now)
    collected_via: str = "local"  # "local" | "ssh:<alias>"
    telemetry_sources: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Deployment configuration (goal.md §9)
# ---------------------------------------------------------------------------
class TokenizerInfo(BaseModel):
    source: str = "unknown"  # explicit, model-metadata, cache, hf-compat, engine
    name: Optional[str] = None
    certainty: str = "unknown"  # high, medium, low, unknown
    vocab_size: Optional[int] = None


class DeploymentConfig(BaseModel):
    """Structured, normalized serving configuration.

    `normalized` holds engine-specific fields; `raw_command` is the
    sanitized original startup command (goal.md §9).
    """

    engine: str = "unknown"
    engine_version: Optional[str] = None
    engine_image: Optional[str] = None  # container image/tag/digest
    model: str = ""
    model_revision: Optional[str] = None
    quantization: Optional[str] = None
    dtype: Optional[str] = None
    kv_cache_dtype: Optional[str] = None
    max_model_len: Optional[int] = None
    gpu_memory_utilization: Optional[float] = None
    max_num_seqs: Optional[int] = None
    max_batched_tokens: Optional[int] = None
    tensor_parallel: Optional[int] = None
    prefix_caching: Optional[bool] = None
    chunked_prefill: Optional[bool] = None
    speculative_decoding: Optional[str] = None  # e.g. "mtp", "eagle"
    mtp_config: Optional[str] = None
    attention_backend: Optional[str] = None
    enforce_eager: Optional[bool] = None
    async_scheduling: Optional[bool] = None
    compile_options: Optional[str] = None
    scheduler_config: Optional[str] = None
    served_model_name: Optional[str] = None
    tokenizer: Optional[str] = None
    generation_config: Optional[str] = None
    all_args: list[str] = Field(default_factory=list)
    env_vars: dict[str, str] = Field(default_factory=dict)
    raw_command: Optional[str] = None
    normalized: dict[str, Any] = Field(default_factory=dict)

    def meaningful_fields(self) -> dict[str, Any]:
        """Fields used to derive the deterministic configuration ID."""
        return {k: v for k, v in self.model_dump().items() if v not in (None, "", [], {})}


# ---------------------------------------------------------------------------
# Telemetry (goal.md §21)
# ---------------------------------------------------------------------------
class TelemetrySample(BaseModel):
    ts: float  # epoch seconds
    gpu_utilization_pct: Optional[float] = None
    sm_activity_pct: Optional[float] = None
    tensor_pipe_activity_pct: Optional[float] = None
    dram_activity_pct: Optional[float] = None
    mem_ctrl_activity_pct: Optional[float] = None
    vram_used_mib: Optional[float] = None
    vram_free_mib: Optional[float] = None
    sm_clock_mhz: Optional[float] = None
    mem_clock_mhz: Optional[float] = None
    power_watts: Optional[float] = None
    gpu_temp_c: Optional[float] = None
    mem_temp_c: Optional[float] = None
    pcie_rx_mbs: Optional[float] = None
    pcie_tx_mbs: Optional[float] = None
    throttle_reasons: Optional[str] = None
    xid_events: Optional[str] = None
    host_ram_used_gib: Optional[float] = None
    host_load1: Optional[float] = None


class TelemetrySeries(BaseModel):
    """Raw time-series for a benchmark window (§21, §27)."""

    sample_interval_s: float = 1.0
    source: str = "nvidia-smi"  # nvidia-smi | nvml | dcgm | mixed
    samples: list[TelemetrySample] = Field(default_factory=list)

    def aggregate(
        self,
        field: str,
    ) -> tuple[Optional[float], Optional[float], Optional[float]]:
        """Return (mean, max, min) of a TelemetrySample field over samples."""
        vals = [
            getattr(s, field)
            for s in self.samples
            if getattr(s, field, None) is not None
        ]
        if not vals:
            return None, None, None
        mean = sum(vals) / len(vals)
        return mean, max(vals), min(vals)


# ---------------------------------------------------------------------------
# Manifest (goal.md §30)
# ---------------------------------------------------------------------------
class SummaryKpis(BaseModel):
    """Headline KPIs for the run report (goal.md §34)."""

    model: str = ""
    gpu: str = ""
    engine: str = ""
    engine_version: Optional[str] = None
    quantization: Optional[str] = None
    max_context: Optional[int] = None
    peak_decode_tps: Optional[float] = None
    peak_prefill_tps: Optional[float] = None
    best_ttft_ms: Optional[float] = None
    peak_aggregate_tps: Optional[float] = None
    max_stable_concurrency: Optional[int] = None
    peak_vram_gib: Optional[float] = None
    average_power_watts: Optional[float] = None
    tokens_per_joule: Optional[float] = None
    integrity_state: str = VALID


class RunManifest(BaseModel):
    """Authoritative index of a benchmark run (goal.md §30)."""

    schema_version: str = "1.0.0"
    benchmark_suite_version: str = ""
    scoring_version: str = ""
    report_generator_version: str = ""

    # Identity
    run_id: str = ""
    configuration_id: str = ""
    run_label: Optional[str] = None
    configuration_label: Optional[str] = None
    started_at: datetime = Field(default_factory=utc_now)
    finished_at: Optional[datetime] = None
    duration_s: Optional[float] = None

    # Model / engine
    model: str = ""
    model_family: Optional[str] = None
    model_revision: Optional[str] = None
    quantization: Optional[str] = None
    engine: str = ""
    engine_version: Optional[str] = None
    engine_startup_flags: list[str] = Field(default_factory=list)
    deployment: Optional[DeploymentConfig] = None

    # Hardware
    hardware: Optional[HardwareInfo] = None

    # Environment
    os_version: Optional[str] = None
    python_version: Optional[str] = None
    git_commit: Optional[str] = None
    dependencies: dict[str, str] = Field(default_factory=dict)
    tokenizer: Optional[TokenizerInfo] = None
    random_seed: Optional[int] = None

    # Workload
    mode: BenchmarkMode = BenchmarkMode.LIGHT
    budget_s: Optional[float] = None
    workload_dimensions: dict[str, Any] = Field(default_factory=dict)

    # Sources
    telemetry_sources: list[str] = Field(default_factory=list)
    server_metrics_sources: list[str] = Field(default_factory=list)
    aiperf_version: Optional[str] = None

    # Integrity + artifacts
    integrity_state: str = VALID
    integrity_reasons: list[str] = Field(default_factory=list)
    artifacts: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
