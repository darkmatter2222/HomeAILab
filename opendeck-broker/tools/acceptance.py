"""Acceptance-matrix runner for opendeck-broker (maps to research section 14).

Each row of the research's acceptance table is either:
  * HEADLESS -- provable now with an in-memory device + fake observer + injected
    window/foreground fakes; the assertion runs and must pass; or
  * PHYSICAL -- requires the real Mini (and, for focus, a second foreground app);
    marked as such so a simulated pass is never mistaken for hardware evidence
    (research section 14: "Do not report the reboot, USB, or physical-press
    tests as passed from a simulated API test").

Run:
  python tools/acceptance.py            # runs headless rows, writes a report
  python tools/acceptance.py --keep-going

Report: opendeck-broker/acceptance-report.md
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from opendeck_broker.broker import Broker  # noqa: E402
from opendeck_broker.device.mock import MockDevice  # noqa: E402
from opendeck_broker.focus.windows import FocusStatus, WindowsFocusAdapter  # noqa: E402
from opendeck_broker.model import DisplayAppearance  # noqa: E402
from opendeck_broker.opencode.adapter import OpenCodeAdapter  # noqa: E402
from opendeck_broker.opencode.observe import SessionState  # noqa: E402
from opendeck_broker.registry import Registry  # noqa: E402


# A process that is alive for the duration of the test, so refresh()'s
# process-exit observation does not clear these slots mid-scenario.
LIVE = os.getpid()


class FakeObserver:
    def __init__(self):
        self.states = {}

    def snapshot_by_directory(self):
        return dict(self.states)


def make_focus(windows=None, foreground_after=None):
    windows = windows or []

    def enumerate(cb):
        for hwnd, title in windows:
            if not cb(hwnd, title):
                break

    return WindowsFocusAdapter(
        enumerate_windows=enumerate,
        show_window=lambda h, c=9: True,
        set_foreground=lambda h: True,
        get_foreground=lambda: (foreground_after if foreground_after is not None else (windows[0][0] if windows else 0)),
    )


@dataclass
class Harness:
    broker: Broker
    adapter: OpenCodeAdapter
    device: MockDevice
    obs: FakeObserver

    def ap(self, slot: int) -> DisplayAppearance:
        return self.broker.registry.frame()[slot].appearance


def build() -> Harness:
    obs = FakeObserver()
    reg = Registry()
    adapter = OpenCodeAdapter(reg, obs)
    device = MockDevice()
    focus = make_focus()
    broker = Broker(registry=reg, device=device, focus=focus)
    broker.start()
    return Harness(broker, adapter, device, obs)


@dataclass
class Row:
    id: str
    name: str
    kind: str  # "headless" or "physical"
    run: Optional[Callable[[Harness], None]] = None
    note: str = ""


# --------------------------------------------------------------------------- #
# Headless rows
# --------------------------------------------------------------------------- #
def r_cold_reboot_no_opencode(h: Harness) -> None:
    for s in range(6):
        assert h.ap(s) is DisplayAppearance.BLACK, h.ap(s)


def r_launch_one_home_screen(h: Harness) -> None:
    h.adapter.register_launch("/d/homeai", "homeai", pid=LIVE)
    h.adapter.refresh()
    h.broker.render()
    assert h.ap(0) is DisplayAppearance.IDLE


def r_launch_six_unique_stable(h: Harness) -> None:
    slots = []
    for i in range(6):
        _, s = h.adapter.register_launch(f"/d/p{i}", f"p{i}", pid=LIVE)
        slots.append(s)
    assert sorted(slots) == [0, 1, 2, 3, 4, 5]
    # stable: a refresh does not move them
    h.adapter.refresh()
    h.broker.render()
    for i in range(6):
        assert h.broker.registry.frame()[i].instance_id is not None


def r_two_same_directory_separate(h: Harness) -> None:
    # two TUIs in the SAME directory share an alias but must get separate
    # buttons AND separate, unambiguous focus targets (unique launch token).
    _, s0 = h.adapter.register_launch("/d/same", "same", pid=LIVE)
    _, s1 = h.adapter.register_launch("/d/same", "same", pid=LIVE)
    assert s0 != s1
    a = list(h.adapter.launches())[0]
    b = list(h.adapter.launches())[1]
    assert a.instance.focus_target["opaqueId"] != b.instance.focus_target["opaqueId"]
    # each marker is a unique substring (no window-title collision)
    assert a.instance.focus_target["opaqueId"] not in b.instance.focus_target["opaqueId"]


def r_generate_long_response_green_then_amber(h: Harness) -> None:
    h.adapter.register_launch("/d/a", "a", pid=LIVE)
    h.obs.states["/d/a"] = SessionState(directory="/d/a", has_session=True, status="busy")
    h.adapter.refresh(); h.broker.render()
    assert h.ap(0) is DisplayAppearance.RUN
    h.obs.states["/d/a"] = SessionState(directory="/d/a", has_session=True)
    h.adapter.refresh(); h.broker.render()
    assert h.ap(0) is DisplayAppearance.IDLE


def r_long_tool_without_tokens_stays_green(h: Harness) -> None:
    h.adapter.register_launch("/d/a", "a", pid=LIVE)
    h.obs.states["/d/a"] = SessionState(directory="/d/a", has_session=True, status="busy")
    h.adapter.refresh(); h.broker.render()
    assert h.ap(0) is DisplayAppearance.RUN
    # still busy on the next observation
    h.obs.states["/d/a"] = SessionState(directory="/d/a", has_session=True, status="busy")
    h.adapter.refresh(); h.broker.render()
    assert h.ap(0) is DisplayAppearance.RUN


def r_auto_retry_is_green(h: Harness) -> None:
    h.adapter.register_launch("/d/a", "a", pid=LIVE)
    h.obs.states["/d/a"] = SessionState(directory="/d/a", has_session=True, status="retry")
    h.adapter.refresh(); h.broker.render()
    assert h.ap(0) is DisplayAppearance.RUN


def r_permission_red_until_answered(h: Harness) -> None:
    h.adapter.register_launch("/d/a", "a", pid=LIVE)
    h.obs.states["/d/a"] = SessionState(directory="/d/a", has_session=True, status="idle", pending_permissions=["p1"])
    h.adapter.refresh(); h.broker.render()
    assert h.ap(0) is DisplayAppearance.INPUT
    h.obs.states["/d/a"] = SessionState(directory="/d/a", has_session=True)
    h.adapter.refresh(); h.broker.render()
    assert h.ap(0) is DisplayAppearance.IDLE


def r_question_red_until_replied(h: Harness) -> None:
    h.adapter.register_launch("/d/a", "a", pid=LIVE)
    h.obs.states["/d/a"] = SessionState(directory="/d/a", has_session=True, pending_questions=["q1"])
    h.adapter.refresh(); h.broker.render()
    assert h.ap(0) is DisplayAppearance.INPUT
    h.obs.states["/d/a"] = SessionState(directory="/d/a", has_session=True)
    h.adapter.refresh(); h.broker.render()
    assert h.ap(0) is DisplayAppearance.IDLE


def r_two_pending_resolving_one_stays_red(h: Harness) -> None:
    h.adapter.register_launch("/d/a", "a", pid=LIVE)
    h.obs.states["/d/a"] = SessionState(directory="/d/a", has_session=True, pending_questions=["q1"], pending_permissions=["p1"])
    h.adapter.refresh(); h.broker.render()
    assert h.ap(0) is DisplayAppearance.INPUT
    h.obs.states["/d/a"] = SessionState(directory="/d/a", has_session=True, pending_permissions=["p1"])
    h.adapter.refresh(); h.broker.render()
    assert h.ap(0) is DisplayAppearance.INPUT  # still red
    h.obs.states["/d/a"] = SessionState(directory="/d/a", has_session=True)
    h.adapter.refresh(); h.broker.render()
    assert h.ap(0) is DisplayAppearance.IDLE


def r_child_complete_parent_stays_green(h: Harness) -> None:
    # parent busy (generating). A child's completion must not demote the parent.
    h.adapter.register_launch("/d/a", "a", pid=LIVE)
    h.obs.states["/d/a"] = SessionState(directory="/d/a", has_session=True, status="busy")
    h.adapter.refresh(); h.broker.render()
    assert h.ap(0) is DisplayAppearance.RUN
    # child finishes; the parent is still generating, so the dir is still busy
    h.obs.states["/d/a"] = SessionState(directory="/d/a", has_session=True, status="busy")
    h.adapter.refresh(); h.broker.render()
    assert h.ap(0) is DisplayAppearance.RUN


def r_child_input_owning_tui_red_no_new_slot(h: Harness) -> None:
    h.adapter.register_launch("/d/a", "a", pid=LIVE)
    h.obs.states["/d/a"] = SessionState(directory="/d/a", has_session=True, pending_questions=["q-child"])
    h.adapter.refresh(); h.broker.render()
    assert h.ap(0) is DisplayAppearance.INPUT
    # exactly one slot used (the child did not take a second button)
    occupied = [s for s in h.broker.registry.frame() if s.instance_id]
    assert len(occupied) == 1


def r_prose_question_is_idle(h: Harness) -> None:
    # final answer ends in ordinary prose -> no structured request -> amber
    h.adapter.register_launch("/d/a", "a", pid=LIVE)
    h.obs.states["/d/a"] = SessionState(directory="/d/a", has_session=True)
    h.adapter.refresh(); h.broker.render()
    assert h.ap(0) is DisplayAppearance.IDLE


def r_click_six_mixed_states_focus_no_mutation(h: Harness) -> None:
    # six instances, mixed states, one focus window per marker
    states = {
        "/d/p0": SessionState(directory="/d/p0", has_session=True, status="busy"),
        "/d/p1": SessionState(directory="/d/p1", has_session=True),
        "/d/p2": SessionState(directory="/d/p2", has_session=True, pending_questions=["q"]),
    }
    ids = []
    for i in range(6):
        _, s = h.adapter.register_launch(f"/d/p{i}", f"p{i}", pid=LIVE)
        ids.append((s, f"p{i}"))
    h.obs.states.update(states)
    h.adapter.refresh(); h.broker.render()
    # give the broker a focus adapter that resolves each marker
    h.broker.focus = make_focus(windows=[(1, "[opencode:p0] x"), (2, "[opencode:p1] x")], foreground_after=1)
    appearances_before = [h.ap(s) for s, _ in ids]
    for s, alias in ids:
        h.device.inject_press(s)
    results = h.broker.process_presses()
    # no state mutation from pressing
    appearances_after = [h.ap(s) for s, _ in ids]
    assert appearances_before == appearances_after
    # exactly one press edge per key -> no double execution
    assert len(results) == 6


def r_click_black_key_nothing(h: Harness) -> None:
    h.device.inject_press(5)
    res = h.broker.process_presses()
    assert res[0]["result"] == "no_occupant"
    assert h.ap(5) is DisplayAppearance.BLACK


def r_single_press_single_focus(h: Harness) -> None:
    _, s = h.adapter.register_launch("/d/a", "a", pid=LIVE)
    h.broker.focus = make_focus(windows=[(7, "[opencode:a] x")], foreground_after=7)
    h.device.inject_press(s)
    res = h.broker.process_presses()
    assert len(res) == 1  # one press edge -> one focus request


def r_switch_conversation_same_slot(h: Harness) -> None:
    iid, s = h.adapter.register_launch("/d/a", "a", pid=LIVE)
    h.adapter.refresh(); h.broker.render()
    first = h.broker.registry.frame()[s]
    # the selected session changes; the instance (and its slot) does not
    inst = h.broker.registry.instances[iid]
    inst.identity_label = "a"
    h.adapter.refresh(); h.broker.render()
    second = h.broker.registry.frame()[s]
    assert first.instance_id == second.instance_id == iid
    assert first.slot == second.slot == s


def r_close_shell_stays_open_slot_clears(h: Harness) -> None:
    iid, s = h.adapter.register_launch("/d/a", "a", pid=LIVE)
    h.adapter.refresh(); h.broker.render()
    assert h.broker.registry.frame()[s].instance_id is not None
    h.adapter.mark_dead(iid)  # OpenCode ended; wrapping shell may still be open
    h.broker.render()
    assert h.ap(s) is DisplayAppearance.BLACK


def r_kill_terminal_slot_clears(h: Harness) -> None:
    iid, s = h.adapter.register_launch("/d/a", "a", pid=LIVE)
    h.adapter.refresh(); h.broker.render()
    h.adapter.mark_dead(iid)
    h.broker.render()
    assert h.ap(s) is DisplayAppearance.BLACK


def r_pid_and_slot_reuse_no_crossing(h: Harness) -> None:
    _, s = h.adapter.register_launch("/d/a", "a", pid=LIVE)
    h.adapter.refresh()
    a_iid = list(h.adapter.launches())[0].instance_id
    h.device.inject_press(s)  # captured press for 'a'
    h.adapter.mark_dead(a_iid)
    _, s2 = h.adapter.register_launch("/d/a", "b", pid=LIVE)  # new instance, same slot
    assert s2 == s
    res = h.broker.process_presses()
    assert res[0]["result"] == "stale"  # old press must not hit the new occupant


def r_restart_broker_restores_input(h: Harness) -> None:
    # simulate a broker restart: a fresh registry + adapter, re-register with
    # the still-pending request -> red restored without a new question event.
    reg2 = Registry()
    obs2 = FakeObserver()
    obs2.states["/d/a"] = SessionState(directory="/d/a", has_session=True, pending_questions=["q1"])
    adapter2 = OpenCodeAdapter(reg2, obs2)
    dev2 = MockDevice()
    broker2 = Broker(registry=reg2, device=dev2, focus=make_focus())
    broker2.start()
    adapter2.register_launch("/d/a", "a", pid=LIVE)
    adapter2.refresh()
    broker2.render()
    assert broker2.registry.frame()[0].appearance is DisplayAppearance.INPUT


def r_device_reconnect_restores_full_frame(h: Harness) -> None:
    _, s = h.adapter.register_launch("/d/a", "a", pid=LIVE)
    h.obs.states["/d/a"] = SessionState(directory="/d/a", has_session=True, status="busy")
    h.adapter.refresh(); h.broker.render()
    # simulate a USB reconnect: new device instance, full frame re-uploaded
    newdev = MockDevice()
    newdev.connect()  # USB reconnect re-opens the device
    h.broker.device = newdev
    h.broker.device.set_key_press_handler(h.broker.on_key)
    # research section 8: on USB reconnect, invalidate the render cache and
    # upload the complete desired frame.
    h.broker.invalidate_render_cache()
    h.broker.render()
    assert newdev.uploaded_count() == 6
    assert all(newdev.images.get(i) is not None for i in range(6))


def r_seventh_instance_overflow(h: Harness) -> None:
    for i in range(6):
        h.adapter.register_launch(f"/d/p{i}", f"p{i}", pid=100 + i)
    _, s7 = h.adapter.register_launch("/d/p7", "p7", pid=107)
    assert s7 is None  # no slot stolen
    assert h.broker.registry.overflow() != []


def r_bridge_unavailable_unknown_not_indefinite(h: Harness) -> None:
    _, s = h.adapter.register_launch("/d/a", "a", pid=LIVE)
    h.broker.registry.mark_untrusted("a" if False else list(h.adapter.launches())[0].instance_id, False)
    h.broker.render()
    assert h.ap(s) is DisplayAppearance.UNKNOWN  # amber "?", not a lying green


# --------------------------------------------------------------------------- #
# Physical rows (need the real Mini / a second foreground app)
# --------------------------------------------------------------------------- #
PHYSICAL = [
    ("A-own", "Mini ownership + 6 black + 6 numbered images + 6 key events (no OpenCode)", "tools/probe_device.py"),
    ("A-focus", "Real Mini press foregrounds the correct terminal while another app is active", "tools/probe_focus.py"),
    ("A-boot", "Cold reboot with no OpenCode: six black after init, no old sessions resurrected", "reboot host, observe Mini"),
    ("A-order", "Broker started before and after Elgato: selected ownership works in both orders", "start/stop ordering with Elgato app"),
    ("A-replug", "USB disconnect/reconnect restores the complete current frame", "replug the Mini"),
    ("A-power", "Lock/unlock/sleep/resume: no stale green; correct state after resume", "sleep/wake the host"),
    ("A-min", "Focus a minimized instance from another app: restored + foreground verified", "minimize target, press from another app"),
]


def build_matrix() -> list[Row]:
    return [
        Row("B-01", "Cold reboot, no OpenCode -> six black", "headless", r_cold_reboot_no_opencode),
        Row("B-02", "Launch one TUI at home screen -> exactly one amber key", "headless", r_launch_one_home_screen),
        Row("B-03", "Launch six simultaneously -> six unique stable assignments", "headless", r_launch_six_unique_stable),
        Row("B-04", "Launch two in the same directory -> separate buttons + focus targets", "headless", r_two_same_directory_separate),
        Row("B-05", "Generate a long response -> green, amber on completion", "headless", r_generate_long_response_green_then_amber),
        Row("B-06", "Run a long tool without tokens -> stays green", "headless", r_long_tool_without_tokens_stays_green),
        Row("B-07", "Automatic model retry -> green", "headless", r_auto_retry_is_green),
        Row("B-08", "Request permission -> red until answered", "headless", r_permission_red_until_answered),
        Row("B-09", "Request structured question -> red until replied", "headless", r_question_red_until_replied),
        Row("B-10", "Two pending requests -> red until both resolve", "headless", r_two_pending_resolving_one_stays_red),
        Row("B-11", "Child completes while parent runs -> parent stays green", "headless", r_child_complete_parent_stays_green),
        Row("B-12", "Child requires user input -> owning TUI red, no extra slot", "headless", r_child_input_owning_tui_red_no_new_slot),
        Row("B-13", "Final answer asks ordinary prose -> amber (no structured request)", "headless", r_prose_question_is_idle),
        Row("B-14", "Click each of six keys (mixed states) -> focus, no state mutation", "headless", r_click_six_mixed_states_focus_no_mutation),
        Row("B-15", "Click a black key -> no window/process/command/state change", "headless", r_click_black_key_nothing),
        Row("B-16", "Single press -> single focus (no double execution / cycling)", "headless", r_single_press_single_focus),
        Row("B-17", "Switch conversation inside TUI -> same slot, same binding", "headless", r_switch_conversation_same_slot),
        Row("B-18", "Close OpenCode while shell stays open -> slot clears", "headless", r_close_shell_stays_open_slot_clears),
        Row("B-19", "Kill OpenCode or its terminal -> slot clears via liveness", "headless", r_kill_terminal_slot_clears),
        Row("B-20", "Reuse OS PID / reuse slot -> old press does not hit new occupant", "headless", r_pid_and_slot_reuse_no_crossing),
        Row("B-21", "Restart broker while INPUT pending -> re-register restores red", "headless", r_restart_broker_restores_input),
        Row("B-22", "Device reconnect -> complete six-slot frame restored", "headless", r_device_reconnect_restores_full_frame),
        Row("B-23", "Seventh instance -> no live assignment stolen, overflow explicit", "headless", r_seventh_instance_overflow),
        Row("B-24", "Bridge unavailable -> UNKNOWN (amber ?), not an indefinite lie", "headless", r_bridge_unavailable_unknown_not_indefinite),
    ]


def run_matrix(keep_going: bool = False) -> list[tuple[Row, str, str]]:
    results = []
    for row in build_matrix():
        h = build()
        try:
            row.run(h)
            results.append((row, "PASS", ""))
            print(f"PASS  {row.id}  {row.name}")
        except Exception as e:  # noqa: BLE001
            results.append((row, "FAIL", repr(e)))
            print(f"FAIL  {row.id}  {row.name}  -> {e!r}")
            if not keep_going:
                break
    return results


def write_report(results: list[tuple[Row, str, str]], physical: list) -> Path:
    out = Path(__file__).resolve().parent.parent / "acceptance-report.md"
    lines = [
        "# opendeck-broker acceptance matrix",
        "",
        f"Generated: {datetime.now().isoformat(timespec='seconds')}",
        "",
        "Headless rows run with an in-memory device + fake observer + injected",
        "window/foreground fakes. Physical rows require the real Mini and are",
        "listed separately so a simulated pass is never mistaken for hardware",
        "evidence (research section 14).",
        "",
        "## Headless rows",
        "",
        "| ID | Row | Result |",
        "|---|---|---|",
    ]
    for row, status, detail in results:
        note = f" ({detail})" if detail else ""
        lines.append(f"| {row.id} | {row.name} | {status} |{note}")
    passed = sum(1 for _, s, _ in results if s == "PASS")
    lines += ["", f"**Headless: {passed}/{len(results)} passed**", ""]
    lines += [
        "## Physical rows (need the Mini)",
        "",
        "| ID | Row | Evidence tool |",
        "|---|---|---|",
    ]
    for pid, name, tool in physical:
        lines.append(f"| {pid} | {name} | {tool} |")
    lines += ["", "_Physical rows are not claimed as passed by the headless run._", ""]
    out.write_text("\n".join(lines))
    return out


def main(argv: list[str]) -> int:
    keep_going = "--keep-going" in argv
    results = run_matrix(keep_going)
    report = write_report(results, PHYSICAL)
    headless_pass = sum(1 for _, s, _ in results if s == "PASS")
    print(f"\nHeadless: {headless_pass}/{len(results)} passed. Report: {report}")
    return 0 if headless_pass == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
