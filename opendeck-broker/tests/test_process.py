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
