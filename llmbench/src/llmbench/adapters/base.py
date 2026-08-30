"""Engine adapter interface (goal.md §5).

Adapters encapsulate engine-specific behavior:
* detection (how to identify this engine from metadata/metrics)
* deployment-config normalization (map startup flags to canonical fields)
* /metrics mapping (map engine metric names to canonical metric names)

Adding a new engine = subclassing EngineAdapter; no project redesign.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

from ..schemas import DeploymentConfig


class EngineAdapter(ABC):
    """Base class for engine-specific adapters."""

    name: str = "generic"

    @abstractmethod
    def detect(self, meta: dict) -> float:
        """Return a confidence score 0..1 that this engine serves the target.

        ``meta`` contains whatever endpoint metadata, /metrics lines, and
        process info are available.
        """

    @abstractmethod
    def normalize_config(
        self,
        raw_args: list[str],
        env: dict[str, str],
        meta: dict,
    ) -> DeploymentConfig:
        """Build a normalized DeploymentConfig from raw startup state."""

    # Optional overrides --------------------------------------------------
    def metric_mapping(self) -> dict[str, str]:
        """Map canonical metric -> engine metric name (or "" if n/a)."""
        return {}

    def is_chat_completions_supported(self) -> bool:
        return True

    def ignore_eos_supported(self) -> bool:
        return False

    def min_tokens_supported(self) -> bool:
        return False

    def extra_generation_params(self) -> dict[str, Any]:
        """Extra body fields the engine needs (e.g. vLLM ignore_eos=True
        for exact-length generation).  Merged into the request payload."""
        return {}


@dataclass
class EndpointMeta:
    """Everything discovered about the target endpoint."""

    base_url: str = ""
    model: str = ""
    model_max_len: Optional[int] = None
    engine_hints: list[str] = field(default_factory=list)
    metrics_lines: list[str] = field(default_factory=list)
    proc_cmdline: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    version: Optional[str] = None
    image: Optional[str] = None
    raw: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "base_url": self.base_url,
            "model": self.model,
            "model_max_len": self.model_max_len,
            "engine_hints": self.engine_hints,
            "version": self.version,
            "image": self.image,
            "n_metrics_lines": len(self.metrics_lines),
        }
