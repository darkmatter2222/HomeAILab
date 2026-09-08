from opendeck_broker.broker import Broker
from opendeck_broker.device.mock import MockDevice
from opendeck_broker.focus.windows import FocusStatus, WindowsFocusAdapter
from opendeck_broker.model import DisplayAppearance
from opendeck_broker.opencode.adapter import OpenCodeAdapter
from opendeck_broker.opencode.observe import SessionState
from opendeck_broker.registry import Registry


class FakeObserver:
    def __init__(self):
        self.states = {}

    def snapshot_by_directory(self):
        return dict(self.states)


def focus_for(windows, foreground_after=None):
    def enumerate(cb):
        for hwnd, title in windows:
            if not cb(hwnd, title):
                break

    return WindowsFocusAdapter(
        enumerate_windows=enumerate,
        show_window=lambda hwnd, cmd=9: True,
        set_foreground=lambda hwnd: True,
        get_foreground=lambda: foreground_after,
    )


def build(states=None, windows=None, foreground_after=None):
    obs = FakeObserver()
    obs.states = states or {}
    reg = Registry()
    adapter = OpenCodeAdapter(reg, obs)
    device = MockDevice()
    focus = focus_for(windows or [], foreground_after)
    broker = Broker(registry=reg, device=device, focus=focus)
    return broker, adapter, device, obs


def test_start_uploads_six_black():
    broker, *_ = build()
    broker.start()
    assert device_keys(broker) == 6
    # every key got an image (black frame)


def device_keys(broker):
    return broker.device.uploaded_count()


def test_register_render_press_focus_cycle():
    broker, adapter, device, obs = build(
        states={"/d/homeai": SessionState(directory="/d/homeai", has_session=True)},
        windows=[(55, "[opencode:homeai] opencode")],
        foreground_after=55,
    )
    broker.start()
    iid, slot = adapter.register_launch("/d/homeai", "homeai", pid=1)
    adapter.refresh()
    broker.render()

    # idle home session -> amber key, not black
    assert broker.registry.frame()[slot].appearance is DisplayAppearance.IDLE

    # physical press on the occupied slot -> focuses the terminal, no state change
    device.inject_press(slot)
    results = broker.process_presses()
    assert results[0]["result"] == FocusStatus.SUCCESS.value
    status_after = broker.registry.frame()[slot].appearance
    assert status_after is DisplayAppearance.IDLE  # press did not mutate state


def test_press_on_black_key_does_nothing():
    broker, adapter, device, obs = build(windows=[])
    broker.start()
    # no instances: all black. press slot 5.
    device.inject_press(5)
    results = broker.process_presses()
    assert results[0]["result"] == "no_occupant"
    assert broker.registry.frame()[5].appearance is DisplayAppearance.BLACK


def test_running_turns_green_and_completes_to_idle():
    broker, adapter, device, obs = build(windows=[(1, "[opencode:a] x")], foreground_after=1)
    broker.start()
    iid, slot = adapter.register_launch("/d/a", "a", pid=1)
    obs.states["/d/a"] = SessionState(directory="/d/a", has_session=True, status="busy")
    adapter.refresh()
    broker.render()
    assert broker.registry.frame()[slot].appearance is DisplayAppearance.RUN

    obs.states["/d/a"] = SessionState(directory="/d/a", has_session=True)  # idle
    adapter.refresh()
    broker.render()
    assert broker.registry.frame()[slot].appearance is DisplayAppearance.IDLE


def test_two_pending_requests_stay_input_until_both_resolved():
    broker, adapter, device, obs = build()
    broker.start()
    adapter.register_launch("/d/a", "a", pid=1)
    obs.states["/d/a"] = SessionState(
        directory="/d/a", has_session=True, pending_questions=["q1"], pending_permissions=["p1"]
    )
    adapter.refresh()
    broker.render()
    assert broker.registry.frame()[0].appearance is DisplayAppearance.INPUT

    obs.states["/d/a"] = SessionState(directory="/d/a", has_session=True, pending_permissions=["p1"])
    adapter.refresh()
    broker.render()
    assert broker.registry.frame()[0].appearance is DisplayAppearance.INPUT  # still red

    obs.states["/d/a"] = SessionState(directory="/d/a", has_session=True)
    adapter.refresh()
    broker.render()
    assert broker.registry.frame()[0].appearance is DisplayAppearance.IDLE


def test_close_clears_slot_to_black():
    broker, adapter, device, obs = build()
    broker.start()
    iid, slot = adapter.register_launch("/d/a", "a", pid=1)
    adapter.refresh()
    broker.render()
    assert broker.registry.frame()[slot].instance_id is not None

    adapter.mark_dead(iid)
    broker.render()
    assert broker.registry.frame()[slot].appearance is DisplayAppearance.BLACK
    assert broker.registry.frame()[slot].instance_id is None


def test_stale_press_after_slot_reuse():
    broker, adapter, device, obs = build(
        windows=[(1, "[opencode:a] x"), (2, "[opencode:b] y")], foreground_after=2
    )
    broker.start()
    _, s0 = adapter.register_launch("/d/a", "a", pid=1)
    adapter.refresh()
    # capture a press edge for 'a' on slot 0
    device.inject_press(s0)
    # before processing, 'a' dies and 'b' takes the same slot (new generation)
    a_iid = list(adapter.launches())[0].instance_id
    adapter.mark_dead(a_iid)
    b_iid, s1 = adapter.register_launch("/d/a", "b", pid=2)
    assert s1 == s0  # same slot, new generation
    results = broker.process_presses()
    # the delayed press was captured for 'a'; it must not focus 'b'
    assert results[0]["result"] == "stale"
