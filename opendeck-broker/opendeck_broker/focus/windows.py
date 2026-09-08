"""Windows foreground focus adapter.

An OpenCode PID is not necessarily the window-owning PID, and Windows Terminal
may host many tabs. The robust initial supported mode (research section 10) is
one OpenCode TUI per dedicated Windows Terminal window, launched with a stable
title marker (`opencode:<alias>`). A press resolves that marker to a validated
existing window and foregrounds it -- and then *observes* the real foreground
window, because a changed z-order or an API call is not proof of focus.

The Win32 calls are thin module-level functions so unit tests can inject fakes
and run headless (the physical proof is tools/probe_focus.py).
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional


class FocusStatus(str, Enum):
    SUCCESS = "success"
    STALE = "stale"                      # no live assignment for that generation
    NOT_FOUND = "not_found"              # no window matches the marker
    AMBIGUOUS = "ambiguous"              # >1 window matches the marker
    FOCUS_DENIED_OR_WRONG_TARGET = "focus_denied_or_wrong_target"


@dataclass
class FocusResult:
    status: FocusStatus
    hwnd: Optional[int] = None
    observed_foreground: Optional[int] = None
    detail: str = ""


# --------------------------------------------------------------------------- #
# Thin Win32 layer (fakes injectable for tests)
# --------------------------------------------------------------------------- #
def _load_user32():
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    return user32, wintypes


def default_enumerate_windows() -> Callable[[Callable[[int, str], bool], None], None]:
    """Build an EnumWindows scanner that yields (hwnd, title) via callback."""
    user32, wintypes = _load_user32()

    def scan(cb: Callable[[int, str], bool]) -> None:
        import ctypes

        ENUM = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, ctypes.c_void_p)
        buf = ctypes.create_unicode_buffer(512)

        @ENUM
        def _cb(hwnd, _):
            user32.GetWindowTextW(hwnd, buf, 512)
            title = buf.value
            if not user32.IsWindowVisible(hwnd):
                return True
            return cb(hwnd, title)

        user32.EnumWindows(ENUM(_cb), None)

    return scan


def default_show_window(hwnd: int, cmd: int = 9) -> bool:
    user32, _ = _load_user32()
    return bool(user32.ShowWindow(hwnd, cmd))


def default_set_foreground(hwnd: int) -> bool:
    user32, _ = _load_user32()
    return bool(user32.SetForegroundWindow(hwnd))


def default_get_foreground() -> int:
    user32, wintypes = _load_user32()
    return int(user32.GetForegroundWindow())


SW_RESTORE = 9


class WindowsFocusAdapter:
    """Resolve a launch-token marker to a validated window and foreground it."""

    def __init__(
        self,
        enumerate_windows: Optional[Callable] = None,
        show_window: Optional[Callable] = None,
        set_foreground: Optional[Callable] = None,
        get_foreground: Optional[Callable] = None,
    ) -> None:
        self._enumerate = enumerate_windows or default_enumerate_windows()
        self._show = show_window or default_show_window
        self._set_foreground = set_foreground or default_set_foreground
        self._get_foreground = get_foreground or default_get_foreground

    def _windows(self) -> list[tuple[int, str]]:
        out: list[tuple[int, str]] = []

        def cb(hwnd: int, title: str) -> bool:
            out.append((hwnd, title))
            return True  # keep enumerating

        self._enumerate(cb)
        return out

    def resolve(self, marker: str) -> tuple[FocusStatus, list[int]]:
        """Return (status, matching_hwnds) for a title marker."""
        m = marker.lower()
        matches = [h for (h, t) in self._windows() if m in t.lower()]
        if not matches:
            return FocusStatus.NOT_FOUND, matches
        if len(matches) > 1:
            return FocusStatus.AMBIGUOUS, matches
        return FocusStatus.SUCCESS, matches

    def focus(self, hwnd: int) -> FocusResult:
        """Foreground an already-validated window and verify the result."""
        try:
            self._show(hwnd, SW_RESTORE)
            self._set_foreground(hwnd)
        except Exception as e:  # noqa: BLE001
            return FocusResult(FocusStatus.FOCUS_DENIED_OR_WRONG_TARGET, hwnd, detail=str(e))
        observed = self._get_foreground()
        if observed == hwnd:
            return FocusResult(FocusStatus.SUCCESS, hwnd, observed)
        return FocusResult(
            FocusStatus.FOCUS_DENIED_OR_WRONG_TARGET,
            hwnd,
            observed,
            detail=f"requested={hwnd} observed={observed}",
        )

    def focus_marker(self, marker: str) -> FocusResult:
        """Resolve + focus in one call (the broker's press path)."""
        status, matches = self.resolve(marker)
        if status == FocusStatus.NOT_FOUND:
            return FocusResult(FocusStatus.NOT_FOUND, detail=f"no window with marker {marker!r}")
        if status == FocusStatus.AMBIGUOUS:
            return FocusResult(
                FocusStatus.AMBIGUOUS,
                detail=f"{len(matches)} windows match {marker!r}",
            )
        return self.focus(matches[0])


def launch_project(path: str, bat: str, alias: str) -> str:
    """Open a Windows Terminal window running the launcher, with a stable title
    marker. Returns the marker. `--suppressApplicationTitle`-style stability is
    achieved by `cmd /k title <marker>` so the tab title stays the marker."""
    marker = f"opencode:{alias}"
    cmd_line = f"title {marker} opencode & {bat}"
    subprocess.Popen(
        ["wt", "-w", "new", "-d", path, "cmd", "/k", cmd_line],
        stdio=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
    )
    return marker
