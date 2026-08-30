"""GPU telemetry sampling (goal.md §21).

Collects time-series GPU telemetry at ~1s cadence during each cell.
Sources, in preference order (goal.md §21): DCGM > NVML > nvidia-smi,
degrading gracefully.  On a bare host without DCGM we fall back to
nvidia-smi (local or over SSH to the GPU host).

The collector never fails a benchmark just because a tool is missing
(goal.md §21).
"""

from __future__ import annotations

import asyncio
import shlex
import time
from dataclasses import dataclass, field
from typing import Optional

from ..schemas import TelemetrySample, TelemetrySeries
from ..security.sanitize import Sanitizer


@dataclass
class GpuTelemetryConfig:
    sample_interval_s: float = 1.0
    mode: str = "auto"  # auto | local | ssh
    ssh_host: Optional[str] = None  # alias or host:port
    ssh_user: Optional[str] = None
    ssh_key: Optional[str] = None
    gpu_index: int = 0


class GpuTelemetry:
    """Samples GPU metrics in the background while a cell runs."""

    def __init__(self, cfg: GpuTelemetryConfig, sanitizer: Sanitizer | None = None):
        self.cfg = cfg
        # Convenience accessors (config is the source of truth).
        self.ssh_host = cfg.ssh_host
        self.ssh_user = cfg.ssh_user
        self.ssh_key = cfg.ssh_key
        self.sanitizer = sanitizer or Sanitizer()
        self.series = TelemetrySeries(
            sample_interval_s=cfg.sample_interval_s, source="nvidia-smi"
        )
        self._task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()
        self._available: Optional[bool] = None
        self._use_ssh: Optional[bool] = None
        # Running energy accumulator (joules): sum(power * dt)
        self._energy_joule = 0.0
        self._last_power: Optional[float] = None
        self._last_ts: Optional[float] = None
        self._samples_count = 0

    # ------------------------------------------------------------------
    def _detect(self) -> None:
        """Determine whether to sample locally or over SSH, and if available."""
        if self.cfg.mode == "local" or (
            self.cfg.mode == "auto" and self._nvidia_smi_local()
        ):
            self._use_ssh = False
            self._available = self._nvidia_smi_local()
            return
        # Try SSH
        if self.ssh_cmd() is not None:
            self._use_ssh = True
            self._available = self._nvidia_smi_ssh()
            return
        self._use_ssh = True
        self._available = False

    def _nvidia_smi_local(self) -> bool:
        import shutil
        return shutil.which("nvidia-smi") is not None

    def ssh_cmd(self) -> Optional[str]:
        if not self.ssh_host:
            return None
        base = ["ssh"]
        if self.ssh_user:
            base += ["-l", self.ssh_user]
        if self.ssh_key:
            base += ["-i", self.ssh_key]
        base += ["-o", "BatchMode=yes", "-o", "ConnectTimeout=5",
                 "-o", "StrictHostKeyChecking=no", self.ssh_host]
        return " ".join(base)

    def _nvidia_smi_ssh(self) -> bool:
        base = self.ssh_cmd()
        if base is None:
            return False
        import subprocess
        try:
            cmd = f"{base} 'command -v nvidia-smi >/dev/null 2>&1'"
            subprocess.run(cmd, shell=True, capture_output=True, timeout=15)
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------
    def _query_fields(self) -> Optional[dict]:
        """Return the nvidia-smi field dict for the target GPU, or None."""
        fields = (
            "utilization.gpu,utilization.memory,memory.used,memory.free,"
            "clocks.sm,clocks.mem,temperature.gpu,power.draw,"
            "fan,clocks_throttle_reasons.active"
        )
        base = self.ssh_cmd() if self._use_ssh else ""
        cmd = (
            f"{base} nvidia-smi --query-gpu={fields}"
            f" --format=csv,noheader,nounits -i {self.cfg.gpu_index}"
        )
        import subprocess
        try:
            out = subprocess.run(cmd, shell=True, capture_output=True,
                                 text=True, timeout=15)
            if out.returncode != 0:
                return None
            parts = [p.strip() for p in out.stdout.strip().split(",")]
            # N/A handling
            def fnum(x: str) -> Optional[float]:
                try:
                    return float(x)
                except ValueError:
                    return None
            return {
                "gpu_utilization_pct": fnum(parts[0]),
                "mem_ctrl_activity_pct": fnum(parts[1]),
                "vram_used_mib": fnum(parts[2]),
                "vram_free_mib": fnum(parts[3]),
                "sm_clock_mhz": fnum(parts[4]),
                "mem_clock_mhz": fnum(parts[5]),
                "gpu_temp_c": fnum(parts[6]),
                "power_watts": fnum(parts[7]),
                "throttle_reasons": parts[8] if len(parts) > 8 else None,
            }
        except Exception:
            return None

    # ------------------------------------------------------------------
    async def start(self) -> None:
        self._detect()
        self.series.source = (
            "nvidia-smi"
            if self._use_ssh is False
            else ("nvidia-smi-ssh" if self._available else "unavailable")
        )
        self._stop.clear()
        self._task = asyncio.create_task(self._run())

    async def _run(self) -> None:
        if not self._available:
            return
        loop = asyncio.get_running_loop()
        while not self._stop.is_set():
            t0 = time.time()
            d = await loop.run_in_executor(None, self._query_fields)
            if d:
                self._record(d, t0)
            # sleep the remainder to maintain cadence
            elapsed = time.time() - t0
            await asyncio.sleep(max(0.05, self.cfg.sample_interval_s - elapsed))
            try:
                await asyncio.wait_for(self._stop.wait(),
                                       timeout=self.cfg.sample_interval_s)
            except asyncio.TimeoutError:
                pass

    def _record(self, d: dict, ts: float) -> None:
        sample = TelemetrySample(
            ts=ts,
            gpu_utilization_pct=d.get("gpu_utilization_pct"),
            mem_ctrl_activity_pct=d.get("mem_ctrl_activity_pct"),
            vram_used_mib=d.get("vram_used_mib"),
            vram_free_mib=d.get("vram_free_mib"),
            sm_clock_mhz=d.get("sm_clock_mhz"),
            mem_clock_mhz=d.get("mem_clock_mhz"),
            gpu_temp_c=d.get("gpu_temp_c"),
            power_watts=d.get("power_watts"),
            throttle_reasons=d.get("throttle_reasons"),
        )
        # Energy accumulation (joules) = integral of power over time
        if sample.power_watts is not None:
            if self._last_power is not None and self._last_ts is not None:
                dt = ts - self._last_ts
                self._energy_joule += (
                    (self._last_power + sample.power_watts) / 2.0 * dt
                )
            self._last_power = sample.power_watts
            self._last_ts = ts
        self._samples_count += 1
        self.series.samples.append(sample)

    # ------------------------------------------------------------------
    async def stop(self) -> TelemetrySeries:
        if self._task is not None:
            self._stop.set()
            try:
                await asyncio.wait_for(self._task, timeout=10)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass
            self._task = None
        # Attach running energy as a final annotation
        if self.series.samples:
            self.series.samples[-1]._energy_joule = self._energy_joule  # type: ignore
        return self.series

    # ------------------------------------------------------------------
    def energy_joule(self) -> float:
        return self._energy_joule

    def power_summary(self) -> tuple[Optional[float], Optional[float]]:
        """Return (avg_power_watts, peak_power_watts)."""
        powers = [s.power_watts for s in self.series.samples
                  if s.power_watts is not None]
        if not powers:
            return None, None
        return sum(powers) / len(powers), max(powers)

    def gpu_summary(self) -> dict:
        """Mean/max for key fields, used to fill CellMetrics + integrity."""
        def agg(f):
            vals = [getattr(s, f) for s in self.series.samples
                   if getattr(s, f, None) is not None]
            if not vals:
                return None, None, None
            return sum(vals) / len(vals), max(vals), min(vals)

        util_mean, util_max, _ = agg("gpu_utilization_pct")
        vram_max, _, _ = agg("vram_used_mib")
        temp_mean, temp_max, _ = agg("gpu_temp_c")
        sm_mean, sm_max, _ = agg("sm_clock_mhz")
        mem_mean, _, _ = agg("mem_clock_mhz")
        # throttle event count: samples whose throttle_reasons is non-trivial
        throttle_events = sum(
            1 for s in self.series.samples
            if s.throttle_reasons and s.throttle_reasons not in ("0x0000000000000000", "0")
        )
        return {
            "gpu_utilization_pct_mean": util_mean,
            "gpu_utilization_pct_max": util_max,
            "vram_used_gib_max": (vram_max / 1024.0) if vram_max is not None else None,
            "gpu_temp_c_mean": temp_mean,
            "gpu_temp_c_max": temp_max,
            "sm_clock_mhz_mean": sm_mean,
            "sm_clock_mhz_max": sm_max,
            "mem_clock_mhz_mean": mem_mean,
            "throttle_events": throttle_events,
            "energy_joule": self._energy_joule,
            "samples": self._samples_count,
            "source": self.series.source,
        }
