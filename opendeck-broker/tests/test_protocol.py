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


def test_register_launch_uses_provided_focus_target():
    # when a focusTarget with an opaqueId is provided (the realistic launcher
    # path), register_launch uses it as the marker -- not a generated one -- so
    # a later press resolves to this exact window.
    reg, adapter = adapter_with({})
    iid, slot = adapter.register_launch(
        "/d/a", "a", pid=LIVE,
        focus_target={"kind": "windows-terminal-window", "opaqueId": "opencode:custom-marker"},
    )
    inst = reg.instances[iid]
    assert inst.focus_target["opaqueId"] == "opencode:custom-marker"
    assert slot == 0


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


def test_register_launch_normalizes_backslash_directory():
    # register_launch keys the instance by a normalized directory (backslashes ->
    # forward slashes, trailing slash stripped), so a refresh whose observer is
    # keyed the same way matches -- a Windows path and its normalized form agree.
    reg = Registry()
    states = {"C:/proj/win": SessionState(directory="C:/proj/win", has_session=True, status=Status.BUSY)}
    adapter = OpenCodeAdapter(reg, FakeObserver(states))
    iid, slot = adapter.register_launch(r"C:\proj\win", "win", pid=LIVE)
    assert reg.instances[iid].directory == "C:/proj/win"  # backslashes normalized
    adapter.refresh()
    assert reg.frame()[slot].appearance is DisplayAppearance.RUN  # matched via normalized dir


def test_refresh_pushes_pending_permission_to_input():
    # a launch whose directory has a BUSY session with an outstanding permission
    # shows INPUT, not RUN -- the reducer's INPUT-over-RUN precedence holds
    # end-to-end through the adapter's refresh.
    reg, adapter = adapter_with(
        {"/d/a": SessionState(directory="/d/a", has_session=True, status=Status.BUSY, pending_permissions=["p-1"])}
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


def test_each_launch_gets_a_fresh_instance_id():
    # research section 7: "Fresh UUID per launch; immutable identity." Even for
    # the same directory, each launch is a distinct tracked TUI with its own id.
    reg, adapter = adapter_with({})
    i1, _ = adapter.register_launch("/d/a", "a", pid=LIVE)
    i2, _ = adapter.register_launch("/d/a", "a", pid=LIVE)
    i3, _ = adapter.register_launch("/d/a", "a", pid=LIVE)
    assert len({i1, i2, i3}) == 3  # three launches -> three distinct identities
    assert len(reg.instances) == 3


def test_detach_clears_slot():
    reg, adapter = adapter_with({})
    iid, slot = adapter.register_launch("/d/a", "a", pid=LIVE)
    adapter.refresh()
    adapter.detach(iid)
    assert reg.frame()[slot].instance_id is None
    assert reg.frame()[slot].appearance is DisplayAppearance.BLACK


def test_refresh_with_observer_exception_marks_unknown():
    # research section 6: when the bridge (DB read) is unavailable, the TUI's
    # telemetry is untrusted -> UNKNOWN (amber "?"), not a lying green/amber.
    # A refresh that catches the observer's error must mark the launch untrusted.
    reg = Registry()

    class RaisingObserver:
        def snapshot_by_directory(self):
            raise RuntimeError("db lock held")

    adapter = OpenCodeAdapter(reg, RaisingObserver())
    iid, slot = adapter.register_launch("/d/a", "a", pid=LIVE)
    adapter.refresh()
    assert reg.frame()[slot].appearance is DisplayAppearance.UNKNOWN
    # the instance is still tracked (not freed) -- only its trust flag changed
    assert reg.frame()[slot].instance_id == iid


def test_mark_dead_clears_slot():
    reg, adapter = adapter_with({})
    iid, slot = adapter.register_launch("/d/a", "a", pid=LIVE)
    adapter.mark_dead(iid)
    assert reg.frame()[slot].appearance is DisplayAppearance.BLACK


def test_adapter_heartbeat_delegates_to_registry():
    # the adapter's heartbeat is a thin passthrough to the registry: it returns
    # the broker epoch for a known launch and None for an unknown id (so a client
    # can detect a broker restart and re-register).
    reg, adapter = adapter_with({})
    iid, _ = adapter.register_launch("/d/a", "a", pid=LIVE)
    assert adapter.heartbeat(iid) == reg.broker_epoch
    assert adapter.heartbeat("missing") is None


def test_stale_snapshot_rejected_after_reregister_epoch():
    reg, adapter = adapter_with({})
    iid, _ = adapter.register_launch("/d/a", "a", pid=LIVE)
    # a delta from a different producer epoch is rejected
    old = reg.instances[iid]
    assert reg.accept_snapshot(old, "some-other-epoch", old.sequence + 5) is False
    # same epoch, higher seq is accepted
    assert reg.accept_snapshot(old, adapter.producer_epoch, old.sequence + 5) is True
