"""Canonical llmbench data model (versioned Pydantic schemas).

Schema versions
----------------
measurement_schema_version : structure of a measurement cell + its metrics
benchmark_suite_version    : the code that produced the run (suite layout)
scoring_version            : formulas used for score families
report_generator_version   : version that rendered presentation artifacts
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Version constants (defined before `core` is imported)
# ---------------------------------------------------------------------------
MEASUREMENT_SCHEMA_VERSION = "1.0.0"
BENCHMARK_SUITE_VERSION = "0.1.0"
SCORING_VERSION = "1.0.0"
REPORT_GENERATOR_VERSION = "0.1.0"
CONFIG_HASH_ALGO = "sha256"

# Integrity states (goal.md §23)
VALID = "VALID"
VALID_WITH_WARNINGS = "VALID_WITH_WARNINGS"
INVALID = "INVALID"

# Machine-readable integrity reason codes (goal.md §23)
REASON_THERMAL_THROTTLING = "THERMAL_THROTTLING"
REASON_POWER_THROTTLING = "POWER_THROTTLING"
REASON_EXTERNAL_GPU_PROCESS = "EXTERNAL_GPU_PROCESS"
REASON_GPU_OOM = "GPU_OOM"
REASON_SERVER_RESTART = "SERVER_RESTART"
REASON_NETWORK_UNSTABLE = "NETWORK_UNSTABLE"
REASON_LOAD_GENERATOR_SATURATED = "LOAD_GENERATOR_SATURATED"
REASON_INSUFFICIENT_SAMPLES = "INSUFFICIENT_SAMPLES"
REASON_OUTPUT_LENGTH_MISMATCH = "OUTPUT_LENGTH_MISMATCH"
REASON_HIGH_VARIANCE = "HIGH_VARIANCE"
REASON_METRIC_SOURCE_DISAGREEMENT = "METRIC_SOURCE_DISAGREEMENT"
REASON_HTTP_ERRORS = "HTTP_ERRORS"
REASON_CLIENT_CPU_SATURATED = "CLIENT_CPU_SATURATED"
REASON_MEMORY_PRESSURE = "MEMORY_PRESSURE"
REASON_CLOCK_SHIFT = "CLOCK_SHIFT"

from .core import (  # noqa: E402
    BenchmarkMode,
    CacheMode,
    CellMetrics,
    DeploymentConfig,
    Discrepancy,
    GpuInfo,
    HardwareInfo,
    IntegrityResult,
    IntegrityState,
    LoadMode,
    MeasurementCell,
    MeasurementSource,
    MetricDistribution,
    OSInfo,
    RawRequest,
    RunManifest,
    SummaryKpis,
    TelemetrySample,
    TelemetrySeries,
    TokenizerInfo,
    WorkloadCell,
    compute_distribution,
    utc_now,
)

__all__ = [
    "MEASUREMENT_SCHEMA_VERSION",
    "BENCHMARK_SUITE_VERSION",
    "SCORING_VERSION",
    "REPORT_GENERATOR_VERSION",
    "CONFIG_HASH_ALGO",
    "VALID",
    "VALID_WITH_WARNINGS",
    "INVALID",
    "REASON_THERMAL_THROTTLING",
    "REASON_POWER_THROTTLING",
    "REASON_EXTERNAL_GPU_PROCESS",
    "REASON_GPU_OOM",
    "REASON_SERVER_RESTART",
    "REASON_NETWORK_UNSTABLE",
    "REASON_LOAD_GENERATOR_SATURATED",
    "REASON_INSUFFICIENT_SAMPLES",
    "REASON_OUTPUT_LENGTH_MISMATCH",
    "REASON_HIGH_VARIANCE",
    "REASON_METRIC_SOURCE_DISAGREEMENT",
    "REASON_HTTP_ERRORS",
    "REASON_CLIENT_CPU_SATURATED",
    "REASON_MEMORY_PRESSURE",
    "REASON_CLOCK_SHIFT",
    "BenchmarkMode",
    "CacheMode",
    "CellMetrics",
    "DeploymentConfig",
    "Discrepancy",
    "GpuInfo",
    "HardwareInfo",
    "IntegrityResult",
    "IntegrityState",
    "LoadMode",
    "MeasurementCell",
    "MeasurementSource",
    "MetricDistribution",
    "OSInfo",
    "RawRequest",
    "RunManifest",
    "SummaryKpis",
    "TelemetrySample",
    "TelemetrySeries",
    "TokenizerInfo",
    "WorkloadCell",
    "compute_distribution",
    "utc_now",
]
