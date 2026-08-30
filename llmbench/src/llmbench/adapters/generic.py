"""Generic OpenAI-compatible adapter (fallback, goal.md §5)."""

from __future__ import annotations

from ..schemas import DeploymentConfig
from .base import EngineAdapter


class GenericAdapter(EngineAdapter):
    name = "generic-openai"

    def detect(self, meta: dict) -> float:
        # A low default so specific adapters win when their signal is present.
        return 0.15

    def normalize_config(
        self,
        raw_args: list[str],
        env: dict[str, str],
        meta: dict,
    ) -> DeploymentConfig:
        args = raw_args or list(meta.get("proc_cmdline", []))
        cfg = DeploymentConfig(engine=self.name, engine_image=meta.get("image"))
        cfg.all_args = args
        cfg.model = meta.get("model") or ""
        cfg.engine_version = meta.get("version")
        return cfg

    def metric_mapping(self) -> dict[str, str]:
        return {}
