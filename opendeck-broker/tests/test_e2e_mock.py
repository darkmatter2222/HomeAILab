import os

from opendeck_broker.broker import Broker
from opendeck_broker.device.mock import MockDevice
from opendeck_broker.focus.windows import FocusStatus, WindowsFocusAdapter
from opendeck_broker.images import render_key
from opendeck_broker.model import DisplayAppearance
from opendeck_broker.opencode.adapter import OpenCodeAdapter
from opendeck_broker.opencode.observe import SessionState
from opendeck_broker.registry import Registry

# guaranteed-alive pid so refresh()'s process-exit observation keeps the slot
LIVE = os.getpid()


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


def focus_for_instances(broker, iids, foreground_after=None):
    """Build a focus adapter whose windows carry each instance's actual unique
    launch-token marker (the realistic launcher->window-title binding)."""
    windows = []
    for i, iid in enumerate(iids):
        inst = broker.registry.instances.get(iid)
        if inst is None:
            continue
        marker = inst.focus_target["opaqueId"]
        windows.append((100 + i, f"[{marker}] opencode"))
    return focus_for(windows, foreground_after if foreground_after is not None else (100 + (len(iids) - 1) if iids else 0))


def test_start_uploads_six_black():
    broker, *_ = build()
    broker.start()
    assert device_keys(broker) == 6
    # every key got an image (black frame)


def device_keys(broker):
    return broker.device.uploaded_count()


def test_stop_blacks_out_colored_keys():
    # research section 8: graceful shutdown black-outs the keys.
    broker, adapter, device, obs = build(
        states={"/d/a": SessionState(directory="/d/a", has_session=True, status="busy")}
    )
    broker.start()
    iid, slot = adapter.register_launch("/d/a", "a", pid=LIVE)
    adapter.refresh()
    broker.render()
    black = render_key(DisplayAppearance.BLACK, size=broker.image_size)
    assert device.images[slot] != black  # the busy key is colored, not black
    broker.stop()
    for i in range(6):
        assert device.images[i] == black  # every key is blacked out on shutdown
    assert not broker._started


def test_register_render_press_focus_cycle():
    broker, adapter, device, obs = build(
        states={"/d/homeai": SessionState(directory="/d/homeai", has_session=True)}
    )
    broker.start()
    iid, slot = adapter.register_launch("/d/homeai", "homeai", pid=LIVE)
    broker.focus = focus_for_instances(broker, [iid])
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


def test_render_caches_identical_images():
    # research section 11: don't re-upload an unchanged key over USB.
    broker, adapter, device, obs = build(
        states={"/d/a": SessionState(directory="/d/a", has_session=True, status="busy")}
    )
    broker.start()
    iid, slot = adapter.register_launch("/d/a", "a", pid=LIVE)
    adapter.refresh()
    broker.render()
    first = device.set_calls
    assert first >= 1
    # no state change -> a second render uploads nothing new
    adapter.refresh()
    broker.render()
    assert device.set_calls == first
    # a real state change -> exactly that key is re-uploaded
    obs.states["/d/a"] = SessionState(directory="/d/a", has_session=True)  # -> idle
    adapter.refresh()
    broker.render()
    assert device.set_calls == first + 1


def test_press_does_not_change_registration_or_epoch():
    # research section 11: a press only focuses; it must not trigger a new
    # observation epoch or a new instance registration.
    broker, adapter, device, obs = build(
        states={"/d/a": SessionState(directory="/d/a", has_session=True, status="busy")}
    )
    broker.start()
    iid, slot = adapter.register_launch("/d/a", "a", pid=LIVE)
    broker.focus = focus_for_instances(broker, [iid])
    adapter.refresh()
    broker.render()
    count_before = len(broker.registry.instances)
    gen_before = broker.registry.slot_generation(slot)
    appearance_before = broker.registry.frame()[slot].appearance
    # deliver a real press edge and process it (this is where focusing happens)
    device.inject_press(slot)
    results = broker.process_presses()
    assert results[0]["result"] == FocusStatus.SUCCESS.value  # focus actually happened
    # yet the registry was not mutated by the press
    assert len(broker.registry.instances) == count_before  # no new instance
    assert broker.registry.slot_generation(slot) == gen_before  # generation unchanged
    assert broker.registry.frame()[slot].appearance is appearance_before  # state unchanged


def test_raw_hid_poll_emits_press_edges():
    # the raw-HID fallback (no python-elgato-streamdeck) must surface key
    # presses via poll(), since it has no push-based callback thread.
    from opendeck_broker.device.hid_mini import ElgatoMiniHID

    class FakeHid:
        def __init__(self, reports):
            self.reports = list(reports)

        def read(self, n):
            return self.reports.pop(0) if self.reports else b""

    deck = ElgatoMiniHID()
    deck._hid = FakeHid([b"\x00", b"\x03"])  # two buffered press reports (slots 0, 3)
    seen = []
    deck.set_key_press_handler(seen.append)
    deck.poll()
    assert seen == [0, 3]


def test_concurrent_renders_are_serialized():
    # research section 11: serialize image uploads (main loop + REST API can
    # both render). Concurrent renders must not race the cache or leave a torn
    # frame.
    import threading

    broker, adapter, device, obs = build(
        states={"/d/a": SessionState(directory="/d/a", has_session=True, status="busy")}
    )
    broker.start()
    adapter.register_launch("/d/a", "a", pid=LIVE)
    adapter.refresh()
    errors = []

    def worker():
        try:
            for _ in range(50):
                broker.render()
        except Exception as e:  # pragma: no cover - race indicator
            errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    assert all(device.images.get(i) is not None for i in range(6))


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
    iid, slot = adapter.register_launch("/d/a", "a", pid=LIVE)
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
    adapter.register_launch("/d/a", "a", pid=LIVE)
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
    iid, slot = adapter.register_launch("/d/a", "a", pid=LIVE)
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
    _, s0 = adapter.register_launch("/d/a", "a", pid=LIVE)
    adapter.refresh()
    # capture a press edge for 'a' on slot 0
    device.inject_press(s0)
    # before processing, 'a' dies and 'b' takes the same slot (new generation)
    a_iid = list(adapter.launches())[0].instance_id
    adapter.mark_dead(a_iid)
    b_iid, s1 = adapter.register_launch("/d/a", "b", pid=LIVE)
    assert s1 == s0  # same slot, new generation
    results = broker.process_presses()
    # the delayed press was captured for 'a'; it must not focus 'b'
    assert results[0]["result"] == "stale"
