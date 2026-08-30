"""Run-directory layout, atomic writes, config hashing (goal.md §29, §42)."""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import date
from pathlib import Path

from ..schemas import DeploymentConfig
from ..schemas import CONFIG_HASH_ALGO


def slugify(text: str) -> str:
    """Deterministic filesystem slug from a model name."""
    s = text.lower().strip()
    s = re.sub(r"[^a-z0-9.]+", "-", s).strip("-")
    return s or "model"


def configuration_id(config: DeploymentConfig, model_slug: str) -> str:
    """Derive a deterministic, secret-free configuration ID.

    Hashes the meaningful normalized fields (goal.md §29) so two runs of the
    same deployment configuration land in the same configuration directory,
    while different configurations produce different IDs.  Secrets and
    unique machine identifiers are excluded by hashing only the normalized
    fields.
    """
    fields = config.meaningful_fields()
    # Canonical JSON for stable hashing regardless of dict ordering.
    canonical = json.dumps(fields, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"{model_slug}-{digest[:16]}"


def configuration_id_raw(canonical_fields_json: str) -> str:
    digest = hashlib.sha256(canonical_fields_json.encode("utf-8")).hexdigest()
    return digest[:16]


class RunDirectory:
    """Owns the on-disk layout for a single benchmark run.

    benchmarks/<model-slug>/<YYYY-MM-DD>/<configuration-id>/<run-id>/
        ├── manifest.json
        ├── summary.json
        ├── configuration.json
        ├── hardware.json
        ├── integrity.json
        ├── metrics.csv
        ├── metrics.json
        ├── measurements.parquet
        ├── planner.jsonl
        ├── state.json
        ├── run_result.json
        ├── index.html
        ├── raw/
        ├── telemetry/
        ├── charts/
        └── logs/
    """

    def __init__(
        self,
        output_root: str | Path,
        model_slug: str,
        config_id: str,
        run_id: str,
        day: str | None = None,
    ) -> None:
        self.root = Path(output_root)
        self.day = day or date.today().isoformat()
        self.path = (
            self.root / model_slug / self.day / config_id / run_id
        )
        for sub in ("raw", "raw/aiperf", "telemetry", "charts", "logs"):
            (self.path / sub).mkdir(parents=True, exist_ok=True)
        self.path.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # atomic writes (goal.md §42, §54)
    # ------------------------------------------------------------------
    @staticmethod
    def atomic_write_json(dest: Path, obj) -> None:
        """Write JSON via temp-file + rename with fsync for crash safety."""
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(obj, f, indent=2, default=str, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, dest)

    @staticmethod
    def atomic_write_text(dest: Path, text: str) -> None:
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, dest)

    def json_path(self, name: str) -> Path:
        return self.path / name

    def state_path(self) -> Path:
        return self.path / "state.json"

    def planner_path(self) -> Path:
        return self.path / "planner.jsonl"

    def write_state(self, state: dict) -> None:
        self.atomic_write_json(self.state_path(), state)

    def read_state(self) -> dict | None:
        p = self.state_path()
        if not p.exists():
            return None
        with open(p, encoding="utf-8") as f:
            return json.load(f)

    def append_planner(self, entry: dict) -> None:
        with open(self.planner_path(), "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, default=str) + "\n")

    def __repr__(self) -> str:
        return f"RunDirectory({self.path})"
