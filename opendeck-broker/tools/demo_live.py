"""Live end-to-end demo against the REAL OpenCode global DB (no Mini needed).

Distinct from selftest.py (which uses a fake observer): this reads the actual
shared OpenCode store, registers one launch per live directory (the initial
supported mode), and renders the six-slot frame with a mock device. It proves
the full pipeline (DB -> observer -> adapter -> registry -> broker -> render)
works with real OpenCode state. It is not physical evidence: the device is a
mock, so use probe_device.py / probe_focus.py for hardware.

Run:
  python tools/demo_live.py            # uses the default global DB
  OPENCODE_DB=/path/to/opencode.db python tools/demo_live.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from opendeck_broker.broker import Broker  # noqa: E402
from opendeck_broker.device.mock import MockDevice  # noqa: E402
from opendeck_broker.opencode.adapter import OpenCodeAdapter  # noqa: E402
from opendeck_broker.opencode.observe import DbObserver, default_db_path  # noqa: E402
from opendeck_broker.registry import Registry  # noqa: E402


def alias_for(directory: str) -> str:
    tail = directory.rstrip("/").split("/")[-1]
    return tail or "home"


def main() -> int:
    db = default_db_path()
    if not db.exists():
        print(f"no OpenCode global DB at {db}; start OpenCode first")
        return 3
    print(f"OpenCode global DB: {db}")

    obs = DbObserver(db)
    states = obs.snapshot_by_directory()
    print(f"live directories observed: {len(states)}")
    if not states:
        print("no live sessions; the deck would be six black keys")
        return 0

    reg = Registry()
    adapter = OpenCodeAdapter(reg, obs)
    device = MockDevice()
    broker = Broker(registry=reg, device=device)
    broker.start()

    LIVE = os.getpid()
    for d in sorted(states):
        adapter.register_launch(d, alias_for(d), pid=LIVE)
    adapter.refresh()
    broker.render()

    frame = reg.frame()
    print("\n--- rendered frame (mock device) ---")
    for row in (0, 1):
        cells = []
        for col in (0, 1, 2):
            s = row * 3 + col
            st = frame[s]
            ident = (st.label or "-")[:8]
            cells.append(f"[{st.appearance.value:>6} {ident:>8}]")
        print("  " + "  ".join(cells))

    overflow = reg.overflow()
    if overflow:
        print(f"\noverflow (no key, still tracked): {len(overflow)} instance(s)")
    print(f"\nkeys assigned: {sum(1 for s in frame if s.instance_id)} of 6")
    print("\nlive demo complete (real DB, mock device -- not physical evidence).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
