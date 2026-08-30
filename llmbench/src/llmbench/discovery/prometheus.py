"""Prometheus /metrics scraping + engine-metric cross-validation (goal.md §20).

Scrapes the engine's /metrics endpoint directly (no Prometheus server
required) and maps engine metrics into the canonical schema.  Engine
metrics are *compared* against client-observed metrics, never trusted
blindly — discrepancies are surfaced (goal.md §47).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx


@dataclass
class MetricPoint:
    name: str
    labels: dict[str, str] = field(default_factory=dict)
    value: float = 0.0
    help: str = ""
    mtype: str = "gauge"  # gauge | counter | histogram | summary


class PrometheusScraper:
    def __init__(self, url: str, timeout: float = 15.0):
        self.url = url
        self.timeout = timeout
        self.available = False

    def scrape(self) -> dict[str, list[MetricPoint]]:
        """Fetch /metrics; return {metric_name: [points]}."""
        try:
            async_result = asyncio_run(self._scrape_async())
            return async_result
        except Exception:
            self.available = False
            return {}

    async def _scrape_async(self) -> dict[str, list[MetricPoint]]:
        async with httpx.AsyncClient(timeout=httpx.Timeout(self.timeout)) as c:
            r = await c.get(self.url)
            if r.status_code != 200:
                return {}
            text = r.text
        self.available = True
        return parse_prometheus(text)


def parse_prometheus(text: str) -> dict[str, list[MetricPoint]]:
    """Parse Prometheus exposition text into {name: [points]}."""
    out: dict[str, list[MetricPoint]] = {}
    current_help = ""
    current_type = "gauge"
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("# HELP"):
            parts = line.split(" ", 3)
            current_help = parts[3] if len(parts) > 3 else ""
            continue
        if line.startswith("# TYPE"):
            parts = line.split(" ")
            current_type = parts[3] if len(parts) > 3 else "gauge"
            continue
        if line.startswith("#"):
            continue
        # sample line: name{labels} value  [timestamp]
        m = re.match(r"^(\w+)(\{.*\})?\s+([\-\d.eE+]+)", line)
        if not m:
            continue
        name = m.group(1)
        labels_raw = m.group(2) or ""
        value = float(m.group(3))
        labels: dict[str, str] = {}
        if labels_raw:
            inner = labels_raw.strip("{}")
            for part in re.findall(r'(\w+)="([^"]*)"', inner):
                labels[part[0]] = part[1]
        out.setdefault(name, []).append(
            MetricPoint(name=name, labels=labels, value=value,
                        help=current_help, mtype=current_type)
        )
    return out


def metric_value(
    metrics: dict[str, list[MetricPoint]],
    name: str,
    labels: Optional[dict[str, str]] = None,
    aggregate: str = "sum",
) -> Optional[float]:
    """Fetch a single metric value, optionally matching labels.

    ``aggregate`` applies across the matching sample lines:
    * "sum"  - sum over all matching lines (counter/histogram totals)
    * "mean" - mean over matching lines
    * "max"  - max over matching lines
    * "first"- first matching line (no aggregation)
    """
    points = metrics.get(name)
    if not points:
        return None
    if labels:
        matched = [p for p in points
                   if all(p.labels.get(k) == v for k, v in labels.items())]
    else:
        matched = points
    if not matched:
        return None
    vals = [p.value for p in matched]
    if aggregate == "mean":
        return sum(vals) / len(vals)
    if aggregate == "max":
        return max(vals)
    if aggregate == "sum":
        return sum(vals)
    return vals[0]


def asyncio_run(coro):
    """Run an async function synchronously (used from sync contexts)."""
    import asyncio
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop is None:
        return asyncio.run(coro)
    # already inside a loop — run in a fresh thread
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        return ex.submit(asyncio.run, coro).result()
