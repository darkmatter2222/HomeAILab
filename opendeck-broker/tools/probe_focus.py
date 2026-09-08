"""Physical probe: prove a terminal can be focused and the foreground verified.

Build-order step 3. The minimum proof (research section 10): while another app
has focus, resolve the marker to the intended existing window, foreground it,
and observe the real foreground window equals the target.

Usage:
  python tools/probe_focus.py --marker "opencode:homeai"
  python tools/probe_focus.py --launch --alias selftest        # open a test window, then focus it
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from opendeck_broker.focus.windows import FocusStatus, WindowsFocusAdapter, launch_project  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--marker", default=None)
    p.add_argument("--launch", action="store_true")
    p.add_argument("--alias", default="selftest")
    p.add_argument("--path", default=str(Path.cwd()))
    args = p.parse_args()

    marker = args.marker
    if args.launch:
        marker = launch_project(args.path, "opencode", args.alias)
        print(f"launched a test terminal with marker {marker!r}; waiting 2s for it to appear...")
        time.sleep(2.0)

    if not marker:
        print("FAIL: pass --marker 'opencode:<alias>-<id>' or --launch to open a test window first.")
        return 1

    ad = WindowsFocusAdapter()
    status, matches = ad.resolve(marker)
    print(f"resolve({marker!r}) -> {status.value}, matches={len(matches)}")
    if status is not FocusStatus.SUCCESS:
        print(f"FAIL: expected exactly one matching window, got {status.value}.")
        return 1

    res = ad.focus(matches[0])
    print(
        "focus -> "
        f"status={res.status.value} hwnd={res.hwnd} observed_foreground={res.observed_foreground}"
    )
    if res.status is FocusStatus.SUCCESS:
        print("PASS: foreground verified to be the intended window.")
        return 0
    print(f"FAIL: {res.detail}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
