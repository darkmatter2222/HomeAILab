"""Per-user single-instance lock for the broker.

A single broker process must own the Mini (research section 4). On Windows a
named mutex is the cleanest per-user primitive; a lockfile is the portable
fallback. The lock is released on process exit (the named mutex is released
automatically; the lockfile is cleaned up via a finalizer).
"""

from __future__ import annotations

import atexit
import os
import tempfile
from pathlib import Path
from typing import Optional

LOCK_NAME = "Local\\opendeck-broker"


class BrokerLock:
    def __init__(self) -> None:
        self._handle = None
        self._lockfile: Optional[Path] = None

    def acquire(self) -> bool:
        if os.name == "nt":
            return self._acquire_named_mutex()
        return self._acquire_lockfile()

    def _acquire_named_mutex(self) -> bool:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        # A HANDLE is 64-bit; the default c_int restype would truncate it and
        # CloseHandle would then release the wrong handle (leaking the mutex).
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        handle = kernel32.CreateMutexW(None, False, LOCK_NAME)
        last_error = kernel32.GetLastError()
        if handle is None:
            return False
        if last_error == 183:
            # ERROR_ALREADY_EXISTS: another broker owns it. Release OUR handle
            # so we don't keep the mutex alive after the owner releases it.
            kernel32.CloseHandle(handle)
            self._handle = None
            return False
        self._handle = handle
        return True

    def _acquire_lockfile(self) -> bool:
        path = Path(tempfile.gettempdir()) / "opendeck-broker.lock"
        try:
            fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            self._lockfile = path
            atexit.register(self._release_lockfile)
            return True
        except FileExistsError:
            return False

    def _release_lockfile(self) -> None:
        try:
            if self._lockfile and self._lockfile.exists():
                self._lockfile.unlink()
        except Exception:
            pass

    def release(self) -> None:
        if os.name == "nt" and self._handle is not None:
            import ctypes

            kernel32 = ctypes.windll.kernel32
            kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
            kernel32.CloseHandle(self._handle)
            self._handle = None
        else:
            self._release_lockfile()
