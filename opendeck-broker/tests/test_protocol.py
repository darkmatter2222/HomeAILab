import os

from opendeck_broker.model import DisplayAppearance, Status
from opendeck_broker.opencode.adapter import OpenCodeAdapter
from opendeck_broker.opencode.observe import SessionState
from opendeck_broker.registry import Registry

# guaranteed-alive pid so refresh()'s process-exit observation keeps the slot
LIVE = os.getpid()


class FakeObserver:
    def __init__(self, states=None):
        self.states = states or {}

    def snapshot_by_directory(self):
        return dict(self.states)


def adapter_with(states=None):
    reg = Registry()
    adapter = OpenCodeAdapter(reg, FakeObserver(states))
    return reg, adapter


def test_register_launch_gets_slot_and_identity():
    reg, adapter = adapter_with({"/d/homeai": SessionState(directory="/d/homeai", has_session=True)})
    iid, slot = adapter.register_launch("/d/homeai", "homeai", pid=4242)
    assert slot == 0
    inst = reg.instances[iid]
    assert inst.identity_label == "homeai"
    # unique launch token: alias prefix + per-launch suffix
    assert inst.focus_target["opaqueId"].startswith("opencode:homeai-")
    assert inst.process.pid == 4242


def test_refresh_pushes_busy_to_green():
    reg, adapter = adapter_with({"/d/a": SessionState(directory="/d/a", has_session=True, status=Status.BUSY)})
    iid, _ = adapter.register_launch("/d/a", "a", pid=LIVE)
    adapter.refresh()
    assert reg.frame()[0].appearance is DisplayAppearance.RUN


def test_refresh_pushes_pending_question_to_input():
    reg, adapter = adapter_with(
        {"/d/a": SessionState(directory="/d/a", has_session=True, status=Status.IDLE, pending_questions=["q-1"])}
    )
    adapter.register_launch("/d/a", "a", pid=LIVE)
    adapter.refresh()
    assert reg.frame()[0].appearance is DisplayAppearance.INPUT


def test_home_screen_no_session_is_idle_amber():
    # TUI open at its home screen: observer finds no session for the directory
    reg, adapter = adapter_with({})
    adapter.register_launch("/d/fresh", "fresh", pid=LIVE)
    adapter.refresh()
    assert reg.frame()[0].appearance is DisplayAppearance.IDLE


def test_two_launches_same_directory_separate_slots():
    reg, adapter = adapter_with({})
    _, s0 = adapter.register_launch("/d/same", "one", pid=LIVE)
    _, s1 = adapter.register_launch("/d/same", "two", pid=2)
    assert s0 == 0
    assert s1 == 1
    assert len(reg.instances) == 2


def test_detach_clears_slot():
    reg, adapter = adapter_with({})
    iid, slot = adapter.register_launch("/d/a", "a", pid=LIVE)
    adapter.refresh()
    adapter.detach(iid)
    assert reg.frame()[slot].instance_id is None
    assert reg.frame()[slot].appearance is DisplayAppearance.BLACK


def test_mark_dead_clears_slot():
    reg, adapter = adapter_with({})
    iid, slot = adapter.register_launch("/d/a", "a", pid=LIVE)
    adapter.mark_dead(iid)
    assert reg.frame()[slot].appearance is DisplayAppearance.BLACK


def test_stale_snapshot_rejected_after_reregister_epoch():
    reg, adapter = adapter_with({})
    iid, _ = adapter.register_launch("/d/a", "a", pid=LIVE)
    # a delta from a different producer epoch is rejected
    old = reg.instances[iid]
    assert reg.accept_snapshot(old, "some-other-epoch", old.sequence + 5) is False
    # same epoch, higher seq is accepted
    assert reg.accept_snapshot(old, adapter.producer_epoch, old.sequence + 5) is True
