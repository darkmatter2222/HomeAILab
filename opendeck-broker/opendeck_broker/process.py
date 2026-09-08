"""Process liveness for the broker (research sections 6, 7).

Local process-exit observation clears a slot immediately, regardless of any
saved conversation. The broker pairs the PID with the verified process creation
time (when available) so a reused OS PID is not mistaken for the live instance.

psutil is used when present (it is the reliable cross-platform primitive); a
stdlib/ctypes fallback keeps the core dependency-light.
"""

from __future__ import annotations

import os
from typing import Optional

# Windows exit code STILL_ACTIVE (259) means the process has not exited.
_STILL_ACTIVE = 259


def _start_time_ms(pid: int) -> Optional[int]:
    try:
        import psutil

        return int(psutil.Process(pid).create_time() * 1000)
    except Exception:
        return None


def is_alive(pid: int, start_time: Optional[int] = None) -> bool:
    """Return True if the process with this identity is still running.

    `start_time` is a verified creation time (epoch ms). When both this and the
    live process's creation time are known, they must agree; otherwise a pid
    that was recycled to a different process is treated as not-alive for us.
    A non-positive pid (unknown) is treated as alive so we never clear a slot
    because of a missing registration.
    """
    if pid is None or pid <= 0:
        return True

    if _psutil_available():
        return _alive_psutil(pid, start_time)

    if os.name == "nt":
        return _alive_windows(pid, start_time)
    return _alive_posix(pid)


def _psutil_available() -> bool:
    try:
        import psutil  # noqa: F401
        return True
    except Exception:
        return False


def _alive_psutil(pid: int, start_time: Optional[int]) -> bool:
    import psutil

    try:
        p = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return False
    except psutil.AccessDenied:
        return True
    if start_time is not None:
        live_start = int(p.create_time() * 1000)
        if live_start != start_time:
            return False  # recycled pid
    return True


def _alive_windows(pid: int, start_time: Optional[int]) -> bool:
    import ctypes

    k = ctypes.windll.kernel32
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    h = k.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        err = k.GetLastError()
        # ERROR_FILE_NOT_FOUND (2) => dead; ERROR_ACCESS_DENIED (5) => alive.
        return err != 2
    code = ctypes.c_ulong()
    ok = k.GetExitCodeProcess(h, ctypes.byref(code))
    k.CloseHandle(h)
    if not ok:
        return True
    alive = code.value == _STILL_ACTIVE
    if alive and start_time is not None:
        live_start = _start_time_ms(pid)
        if live_start is not None and live_start != start_time:
            return False
    return alive


def _alive_posix(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True
