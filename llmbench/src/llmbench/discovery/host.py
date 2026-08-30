"""Read-only host + hardware introspection (goal.md §8).

Runs locally or over SSH.  Collects OS, CPU, RAM, NUMA, and NVIDIA stack
details.  Gracefully degrades: missing fields are None, not errors.
"""

from __future__ import annotations

import platform
import re
import subprocess
from dataclasses import dataclass
from typing import Optional

import psutil

from ..schemas import GpuInfo, HardwareInfo, OSInfo
from ..security.sanitize import Sanitizer


@dataclass
class HostConfig:
    mode: str = "local"  # local | ssh
    ssh_host: Optional[str] = None
    ssh_user: Optional[str] = None
    ssh_key: Optional[str] = None
    gpu_alias: str = "gpu-host-01"


def _run(cmd: str, timeout: int = 20) -> Optional[str]:
    try:
        out = subprocess.run(cmd, shell=True, capture_output=True,
                             text=True, timeout=timeout)
        return out.stdout if out.returncode == 0 else None
    except Exception:
        return None


def _remote(cfg: HostConfig) -> Optional[str]:
    if cfg.mode != "ssh" or not cfg.ssh_host:
        return None
    parts = ["ssh"]
    if cfg.ssh_user:
        parts += ["-l", cfg.ssh_user]
    if cfg.ssh_key:
        parts += ["-i", cfg.ssh_key]
    parts += ["-o", "BatchMode=yes", "-o", "ConnectTimeout=5",
              "-o", "StrictHostKeyChecking=no", cfg.ssh_host]
    return " ".join(parts)


class HostInspector:
    def __init__(self, cfg: HostConfig, sanitizer: Sanitizer | None = None):
        self.cfg = cfg
        self.sanitizer = sanitizer or Sanitizer()

    def inspect(self) -> HardwareInfo:
        remote = _remote(self.cfg)

        def run(cmd: str) -> Optional[str]:
            full = f"{remote} {cmd}" if remote else cmd
            return _run(full, timeout=25)

        os_info = self._os(run)
        gpus = self._gpus(run)
        hw = HardwareInfo(
            os=os_info,
            gpus=gpus,
            collected_via="local" if not remote else f"ssh:{self.cfg.ssh_host}",
        )
        # Multi-GPU warning (goal.md §6)
        active = [g for g in gpus]
        if len(active) > 1:
            hw.multi_gpu_warning = (
                f"{len(active)} GPUs present; llmbench is optimized for a "
                "single-GPU deployment — results may reflect more than one GPU."
            )
        hw.os.hostname_alias = self.sanitizer.alias_for_host(self.cfg.gpu_alias)
        return hw

    # ------------------------------------------------------------------
    def _os(self, run) -> OSInfo:
        hostname = run("hostname") or "unknown"
        distro = run("grep -m1 PRETTY_NAME /etc/os-release")
        os_line = distro.split("=", 1)[1].strip().strip('"') if distro and "=" in distro else ""
        kernel = run("uname -r") or platform.release()
        arch = run("uname -m") or platform.machine()
        cpu_model = run("grep -m1 'model name' /proc/cpuinfo")
        cpu_model = cpu_model.split(":")[-1].strip() if cpu_model else ""
        phys = run("lscpu | grep -m1 'Socket(s)'")
        cores = run("nproc")
        try:
            ram_gib = psutil.virtual_memory().total / (1024 ** 3)
            swap_gib = psutil.swap_memory().total / (1024 ** 3)
        except Exception:
            ram_gib = swap_gib = None
        uptime = run("cat /proc/uptime")
        uptime_s = float(uptime.split()[0]) if uptime and uptime.split() else None
        numa = run("numactl --hardware 2>/dev/null | grep -c 'available node'")
        hw = OSInfo(
            hostname_alias=self.sanitizer.alias_for_host(hostname),
            os=os_line or "unknown",
            distribution=os_line,
            kernel=kernel or "",
            arch=arch or "",
            uptime_s=uptime_s,
            cpu_model=cpu_model,
            cpu_physical_cores=int(phys.split()[-1]) if phys and phys.split() else None,
            cpu_logical_cores=int(cores) if cores else None,
            ram_gib=ram_gib,
            swap_gib=swap_gib,
            numa_nodes=int(numa) if numa and numa.strip().isdigit() else None,
        )
        return hw

    # ------------------------------------------------------------------
    def _gpus(self, run) -> list[GpuInfo]:
        # Prefer nvidia-smi; degrade to empty list if absent.
        q = ("nvidia-smi --query-gpu="
             "name,driver_version,memory.total,memory.free,memory.used,"
             "temperature.gpu,clocks.max.sm,clocks.max.mem,power.limit,"
             "clocks.current.sm,clocks.current.mem,ecc.enabled,"
             "pcie.link.gen.current,pcie.link.width.current,"
             "pcie.link.gen.max,pcie.link.width.max,mig.current,"
             "--format=csv,noheader,nounits")
        out = run(q)
        if not out:
            # Try to detect any NVIDIA GPU via lspci
            lspci = run("lspci | grep -i nvidia")
            if lspci:
                return [GpuInfo(name="NVIDIA (unspecified)",
                                nvidia_smi_available=False)]
            return []

        drv = run("nvidia-smi --query-gpu=driver_version --format=csv,noheader")
        drv = drv.splitlines()[0].strip() if drv else None
        cuda = run("nvcc --version | grep 'release'")
        cuda_ver = None
        if cuda:
            m = re.search(r"release (\d+\.\d+)", cuda)
            cuda_ver = m.group(1) if m else None
        compute = run("python3 -c 'import torch; print(torch.cuda.get_device_capability(0))' 2>/dev/null")
        cc = None
        if compute:
            m = re.search(r"\((\d+),(\d+)\)", compute)
            cc = f"{m.group(1)}.{m.group(2)}" if m else None

        gpus: list[GpuInfo] = []
        for line in out.splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 14:
                continue

            def fnum(x):
                try:
                    return float(x)
                except ValueError:
                    return None

            def b(x):
                return (x or "").lower() in ("enabled", "true", "on")

            gpu = GpuInfo(
                name=parts[0],
                driver_version=drv,
                memory_gib=(fnum(parts[2]) / 1024.0) if parts[2] not in ("[N/A]",) else None,
                sm_clock_mhz_max=fnum(parts[7]),
                mem_clock_mhz_max=fnum(parts[8]),
                power_limit_watts=fnum(parts[9]),
                temp_limit_c=None,
                pcie_generation=None,
                pcie_width=None,
                pcie_link_gen_current=fnum(parts[12]),
                pcie_link_width_current=fnum(parts[13]),
                ecc_enabled=b(parts[10]) if parts[10] not in ("[N/A]",) else None,
                mig_mode=parts[16] if len(parts) > 16 else None,
                cuda_version=cuda_ver,
                compute_capability=cc,
                nvidia_smi_available=True,
            )
            gpus.append(gpu)
        return gpus
