"""Focus existing Windows top-level windows; never launch from a press."""
import ctypes
from ctypes import wintypes
import os
import time


def activate(record):
    if os.name != "nt":
        return {"ok": False, "reason": "Windows host required"}
    u = ctypes.WinDLL("user32", use_last_error=True)
    u.GetForegroundWindow.restype = wintypes.HWND
    u.IsWindowVisible.argtypes = [wintypes.HWND]
    u.IsIconic.argtypes = [wintypes.HWND]
    u.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    u.SetForegroundWindow.argtypes = [wintypes.HWND]
    u.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    u.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    u.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    u.GetWindowThreadProcessId.restype = wintypes.DWORD
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    u.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
    token = record.get("windowToken", "")
    candidates = []

    @callback_type
    def collect(hwnd, _):
        if not u.IsWindowVisible(hwnd): return True
        text = ctypes.create_unicode_buffer(u.GetWindowTextLengthW(hwnd) + 1)
        u.GetWindowTextW(hwnd, text, len(text))
        pid = wintypes.DWORD()
        u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if (token and text.value == token) or (not token and pid.value == record["process"]["pid"]):
            candidates.append(hwnd)
        return True

    u.EnumWindows(collect, 0)
    if len(candidates) != 1:
        return {"ok": False, "reason": "Window mapping ambiguous or absent; use ocdeck launch for a dedicated window", "matches": len(candidates)}
    hwnd = candidates[0]
    if u.IsIconic(hwnd): u.ShowWindow(hwnd, 9)
    accepted = bool(u.SetForegroundWindow(hwnd))
    for _ in range(5):
        if u.GetForegroundWindow() == hwnd:
            return {"ok": True, "hwnd": int(hwnd), "method": "SetForegroundWindow"}
        time.sleep(.04)
    # Share input queues temporarily with the foreground thread. This is a
    # bounded, same-desktop fallback, not a guarantee of foreground permission.
    # Always detach and independently check the resulting foreground window.
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetCurrentThreadId.restype = wintypes.DWORD
    u.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
    u.BringWindowToTop.argtypes = [wintypes.HWND]
    u.SetFocus.argtypes = [wintypes.HWND]
    u.SetFocus.restype = wintypes.HWND
    current = kernel.GetCurrentThreadId()
    foreground = u.GetForegroundWindow()
    other = u.GetWindowThreadProcessId(foreground, None) if foreground else 0
    attached = False
    try:
        if other and other != current:
            attached = bool(u.AttachThreadInput(current, other, True))
        if attached:
            u.BringWindowToTop(hwnd)
            u.SetForegroundWindow(hwnd)
            u.SetFocus(hwnd)
    finally:
        if attached: u.AttachThreadInput(current, other, False)
    for _ in range(5):
        if u.GetForegroundWindow() == hwnd:
            return {"ok": True, "hwnd": int(hwnd), "method": "AttachThreadInput"}
        time.sleep(.04)
    return {"ok": False, "reason": "Windows denied foreground activation", "hwnd": int(hwnd), "apiAccepted": accepted}
