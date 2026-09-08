"""Compare the real OpenCode session state (global DB) against the on-device
Stream Deck display (app mirror scan) and report whether they match.

Usage:
  python streamdeck/verify_real_state.py
"""

import json
import re
import sqlite3
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DB_PATH = Path.home() / ".local" / "share" / "opencode" / "opencode.db"
RUN_WINDOW_MS = 15_000
MIRROR_SCAN_PS1 = REPO / "opendeck" / "tools" / "verify-deck-physical.ps1"

# Same RAG color map used by the plugin (keyart.js / sessions.js).
STATE_COLOR = {
    "running": (0x2F, 0xD0, 0x6F),
    "idle": (0xF5, 0xB1, 0x3D),
    "waiting": (0xFF, 0x5A, 0x4E),
    "off": (0x5A, 0x5E, 0x6B),
}
STATE_EXPECTED_PIXEL = {
    "running": "GREEN",
    "idle": "AMBER",
    "waiting": "RED",
    "off": "GRAY",
}
TOL = 40


def now_ms() -> int:
    return int(time.time() * 1000)


def derive_state(pending_q: int, last_part_upd_ms, nowms: int) -> str:
    if pending_q and pending_q > 0:
        return "waiting"
    if last_part_upd_ms is not None and nowms - last_part_upd_ms < RUN_WINDOW_MS:
        return "running"
    return "idle"


def db_live_states() -> dict:
    """Per-directory most-recently-active session states (1:1 per agent),
    identical derivation to the opendeck plugin."""
    conn = sqlite3.connect(str(DB_PATH))
    try:
        rows = conn.execute(
            "SELECT s.id, s.directory, s.title, s.time_updated AS upd, "
            "(SELECT MAX(p.time_updated) FROM part p WHERE p.session_id = s.id) AS last_part_upd, "
            "(SELECT COUNT(*) FROM part p WHERE p.session_id = s.id "
            "AND json_extract(p.data,'$.type')='tool' "
            "AND json_extract(p.data,'$.tool')='question' "
            "AND json_extract(p.data,'$.state.status') != 'completed') AS pending_q "
            "FROM session s "
            "WHERE (s.time_archived IS NULL OR s.time_archived = 0) "
            "ORDER BY s.time_updated DESC"
        ).fetchall()
    finally:
        conn.close()

    by_dir = {}
    for sid, directory, title, upd, last_part_upd, pending_q in rows:
        d = (directory or "").replace("\\", "/").rstrip("/")
        cur = by_dir.get(d)
        if cur is None or (upd or 0) > (cur[3] or 0):
            by_dir[d] = (sid, d, title, upd, last_part_upd, pending_q)

    states = {}
    for sid, d, title, upd, last_part_upd, pending_q in by_dir.values():
        states[d] = {
            "state": derive_state(pending_q, last_part_upd, now_ms()),
            "sessionId": sid,
            "title": title,
            "directory": d,
        }
    return states


def mirror_color_scan() -> dict:
    out = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
         "-File", str(MIRROR_SCAN_PS1)],
        capture_output=True, text=True, timeout=120,
    )
    counts = {}
    for line in out.stdout.splitlines():
        m = re.match(r"^(RED|GREEN|BLUE|AMBER|GRAY)\s*:\s*(\d+)\s*sampled pixels", line.strip())
        if m:
            counts[m.group(1)] = int(m.group(2))
    return {"counts": counts}


def main() -> int:
    states = db_live_states()
    scan = mirror_color_scan()
    counts = scan["counts"]

    print("=== REAL session state (from opencode.db) ===")
    for d, s in states.items():
        print(f"  {s['state']:8}  {d}  ({s['title']})")

    print("\n=== Expected on-device colors (from real state) ===")
    expected_colors = set()
    for d, s in states.items():
        expected_colors.add(STATE_EXPECTED_PIXEL[s["state"]])
    for c in sorted(expected_colors):
        src = [s["state"] for s in states.values() if STATE_EXPECTED_PIXEL[s["state"]] == c]
        print(f"  {c} (from {src[0] if src else 'off/empty'})")

    print("\n=== On-device mirror scan (what the device actually shows) ===")
    for name in ("RED", "GREEN", "BLUE", "AMBER", "GRAY"):
        print(f"  {name:6} : {counts.get(name, 0)} sampled pixels")

    found = {k: v for k, v in counts.items() if v > 0}
    stale = set(found) - expected_colors
    missing = expected_colors - set(found)

    print("\n=== Verdict ===")
    print(f"Expected colors: {sorted(expected_colors)}")
    print(f"Shown on device: {sorted(found)}")
    if missing:
        print(f"MATCH: FAIL — expected {sorted(missing)} not found on device (stale/absent)")
        return 1
    if stale:
        print(f"STALE: colors on device not in real state: {sorted(stale)}")
    if not missing and not stale:
        print("MATCH: PASS — device shows exactly the real states (green/amber/gray as appropriate)")
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
