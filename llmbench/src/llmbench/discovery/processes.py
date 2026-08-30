"""Process inspection helpers for deployment-config discovery (goal.md §9)."""

from __future__ import annotations

import os
import re
import subprocess
from typing import Optional


def _list_candidate_pids() -> list[int]:
    """List PIDs whose cmdline contains an LLM-serving keyword.

    Best-effort: only works where /proc is readable (Linux).  Returns [] on
    other platforms or when /proc is unreadable (e.g. Windows, unprivileged).
    """
    candidates = []
    for pid in _all_pids():
        try:
            with open(f"/proc/{pid}/cmdline", "rb") as f:
                cmd = f.read().decode("utf-8", "replace")
            if any(k in cmd.lower() for k in ("vllm", "llama-server", "sglang", "trtllm")):
                candidates.append(pid)
        except Exception:
            continue
    return candidates


def _all_pids() -> list[int]:
    out = []
    try:
        for d in os.listdir("/proc"):
            if d.isdigit():
                out.append(int(d))
    except (FileNotFoundError, NotADirectoryError, PermissionError):
        return []
    return out


def read_cmdline(pid: int) -> list[str]:
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            cmd = f.read().replace(b"\0", b" ").decode("utf-8", "replace").strip()
        return cmd.split()
    except Exception:
        return []


def find_serving_process() -> Optional[int]:
    """Best-effort: the serving process on this host (if local)."""
    pids = _list_candidate_pids()
    return pids[0] if pids else None


def read_env(pid: int) -> dict[str, str]:
    """Read a process's environment (requires root or same-user; best-effort)."""
    env: dict[str, str] = {}
    try:
        with open(f"/proc/{pid}/environ", "rb") as f:
            data = f.read().decode("utf-8", "replace")
        for kv in data.split("\0"):
            if "=" in kv:
                k, v = kv.split("=", 1)
                env[k] = v
    except Exception:
        pass
    return env


def ps_commandline_fallback(keyword: str = "vllm") -> list[str]:
    """Fallback using ps when /proc isn't readable."""
    try:
        out = subprocess.run(
            f"ps -eo args | grep -i {re.escape(keyword)} | grep -v grep | head -1",
            shell=True, capture_output=True, text=True, timeout=10,
        )
        line = out.stdout.strip()
        return line.split() if line else []
    except Exception:
        return []
