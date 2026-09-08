import os
import subprocess
import sys

from opendeck_broker.model import DisplayAppearance
from opendeck_broker.opencode.adapter import OpenCodeAdapter
from opendeck_broker.opencode.observe import SessionState
from opendeck_broker.process import is_alive
from opendeck_broker.registry import Registry


class FakeObserver:
    def __init__(self, states=None):
        self.states = states or {}

    def snapshot_by_directory(self):
        return dict(self.states)


def dead_pid() -> int:
    p = subprocess.Popen([sys.executable, "-c", "pass"])
    p.wait()
    return p.pid


def test_is_alive_true_for_self():
    assert is_alive(os.getpid()) is True


def test_is_alive_false_for_dead():
    assert is_alive(dead_pid()) is False


def test_is_alive_unknown_pid_is_alive():
    # a non-positive / unknown pid must not clear a slot
    assert is_alive(0) is True
    assert is_alive(-1) is True


def test_start_time_ms_live_and_invalid():
    # _start_time_ms returns the creation time (epoch ms) for a live pid and
    # None when the pid cannot be resolved (the PID-reuse guard pairs pid with a
    # verified creation time; a None just means "fall back to pid equality").
    from opendeck_broker.process import _start_time_ms

    live = _start_time_ms(os.getpid())
    assert live is not None
    assert live > 0  # a plausible epoch-ms value

    # an unresolvable pid (negative) returns None, not a crash
    assert _start_time_ms(-1) is None


def test_is_alive_windows_fallback_without_psutil(monkeypatch):
    # when psutil is unavailable, the Windows ctypes fallback must still report
    # a live process as alive, a dead pid as dead, and an unknown pid as safe.
    from opendeck_broker import process as proc

    monkeypatch.setattr(proc, "_psutil_available", lambda: False)
    assert proc.is_alive(os.getpid()) is True
    assert proc.is_alive(dead_pid()) is False
    assert proc.is_alive(0) is True


def test_dead_process_clears_slot_on_refresh():
    reg = Registry()
    adapter = OpenCodeAdapter(reg, FakeObserver())
    pid = dead_pid()
    iid, slot = adapter.register_launch("/d/a", "a", pid=pid)
    adapter.refresh()
    assert reg.frame()[slot].instance_id is None
    assert reg.frame()[slot].appearance is DisplayAppearance.BLACK


def test_live_process_survives_refresh():
    reg = Registry()
    adapter = OpenCodeAdapter(
        reg, FakeObserver({"/d/a": SessionState(directory="/d/a", has_session=True)})
    )
    iid, slot = adapter.register_launch("/d/a", "a", pid=os.getpid())
    adapter.refresh()
    assert reg.frame()[slot].instance_id == iid


def test_pid_reuse_guarded_by_start_time():
    # a recycled pid whose creation time differs is treated as not ours.
    # (psutil exposes create_time; if unavailable this is a no-op guard.)
    import psutil

    live_start = int(psutil.Process(os.getpid()).create_time() * 1000)
    assert is_alive(os.getpid(), live_start) is True
    assert is_alive(os.getpid(), live_start + 1) is False  # mismatched start time


def test_process_matches_pid_and_start_time():
    # dataclass-level reuse-guard identity (model.Process.matches): same pid +
    # same verified start time is the same instance; a recycled pid (different
    # start time) is not. Unknown start time falls back to pid equality.
    from opendeck_broker.model import Process

    a = Process(pid=4242, start_time=1000)
    assert a.matches(Process(pid=4242, start_time=1000)) is True
    assert a.matches(Process(pid=4242, start_time=2000)) is False  # recycled pid
    assert a.matches(Process(pid=9999, start_time=1000)) is False  # different pid
    # unknown start time on either side -> fall back to pid equality
    assert a.matches(Process(pid=4242)) is True
    assert Process(pid=4242).matches(Process(pid=4242, start_time=1234)) is True


def test_recycled_pid_cleared_via_adapter_refresh():
    # end-to-end: the adapter pairs the pid with the verified creation time, so a
    # refresh sees a same-pid whose start time no longer matches (recycled) and
    # clears the slot instead of trusting it.
    import psutil

    reg = Registry()
    adapter = OpenCodeAdapter(reg, FakeObserver())
    pid = os.getpid()
    real_start = int(psutil.Process(pid).create_time() * 1000)
    _, slot = adapter.register_launch("/d/a", "a", pid=pid, start_time=real_start + 1)
    adapter.refresh()
    assert reg.frame()[slot].instance_id is None
    assert reg.frame()[slot].appearance is DisplayAppearance.BLACK
