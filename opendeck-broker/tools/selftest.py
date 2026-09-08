"""Headless end-to-end self-test (SIMULATED, not physical evidence).

Runs the full broker loop with an in-memory device and a fake OpenCode
observer, printing the six-slot frame at each step. Use this to sanity-check
wiring without the Mini attached. For real evidence use probe_device.py and
probe_focus.py.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from opendeck_broker.broker import Broker  # noqa: E402
from opendeck_broker.device.mock import MockDevice  # noqa: E402
from opendeck_broker.focus.windows import WindowsFocusAdapter  # noqa: E402
from opendeck_broker.model import DisplayAppearance  # noqa: E402
from opendeck_broker.opencode.adapter import OpenCodeAdapter  # noqa: E402
from opendeck_broker.opencode.observe import SessionState  # noqa: E402
from opendeck_broker.registry import Registry  # noqa: E402


class FakeObserver:
    def __init__(self):
        self.states = {}

    def snapshot_by_directory(self):
        return dict(self.states)


def print_frame(broker: Broker, title: str) -> None:
    print(f"\n--- {title} ---")
    for row in (0, 1):
        cells = []
        for col in (0, 1, 2):
            s = row * 3 + col
            st = broker.registry.frame()[s]
            ident = (st.label or "-")[:8]
            cells.append(f"[{st.appearance.value:>6} {ident:>8}]")
        print("  " + "  ".join(cells))


def main() -> int:
    obs = FakeObserver()
    reg = Registry()
    adapter = OpenCodeAdapter(reg, obs)
    device = MockDevice()
    focus = WindowsFocusAdapter(
        enumerate_windows=lambda cb: [cb(1, "[opencode:homeai] x") or True, cb(2, "[opencode:ryans] y") or True],
        show_window=lambda h, c=9: True,
        set_foreground=lambda h: True,
        get_foreground=lambda: 1,
    )
    broker = Broker(registry=reg, device=device, focus=focus)
    broker.start()

    print_frame(broker, "cold start: six black")

    LIVE = os.getpid()
    a, sa = adapter.register_launch("/d/homeai", "homeai", pid=LIVE)
    b, sb = adapter.register_launch("/d/ryans", "ryans", pid=LIVE)
    obs.states["/d/homeai"] = SessionState(directory="/d/homeai", has_session=True, status="busy")
    obs.states["/d/ryans"] = SessionState(directory="/d/ryans", has_session=True)
    adapter.refresh()
    broker.render()
    print_frame(broker, "homeai RUNNING (green), ryans IDLE (amber)")

    obs.states["/d/homeai"] = SessionState(directory="/d/homeai", has_session=True, status="idle", pending_questions=["q"])
    adapter.refresh()
    broker.render()
    print_frame(broker, "homeai asks a question -> INPUT (red)")

    device.inject_press(sa)  # press the homeai key
    for r in broker.process_presses():
        print(f"  press slot {r['slot']} -> {r['result']} (hwnd={r.get('hwnd')})")

    adapter.mark_dead(a)
    broker.render()
    print_frame(broker, "homeai closed -> its slot black again")

    print("\nself-test complete (simulated).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
