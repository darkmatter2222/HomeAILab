"""Read the live on-screen state of the Stream Deck without a screenshot.

Mirrors the OpenCode Deck plugin's observation layer:

  opencode.db (sqlite3)   -> per-session last part update + pending questions
  projects.json           -> project alias -> directory mapping
  streamdeck-mcp (profile mode) -> which deck keys host which project

State machine (identical to the plugin):
  waiting  (red)    pending question open (question tool not completed)
  running  (green)   last part update within 15s (active generation/tool)
  idle     (amber)   session alive but quiet
  off      (gray)    no live session for that project's directory

Usage:
  python streamdeck/live_screen.py
"""

import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from fetch_state import McpStdioClient

PLUGIN_DIR = (
    Path.home() / "AppData" / "Roaming" / "Elgato" / "StreamDeck" / "Plugins"
    / "dev.ryans.opendeck.sdPlugin"
)
DB_PATH = Path.home() / ".local" / "share" / "opencode" / "opencode.db"
RUN_WINDOW_MS = 15_000

QUERY = """
SELECT s.id, s.directory, s.title, s.time_updated AS upd,
  (SELECT MAX(p.time_updated) FROM part p WHERE p.session_id = s.id) AS last_part_upd,
  (SELECT COUNT(*) FROM part p WHERE p.session_id = s.id
     AND json_extract(p.data,'$.type')='tool'
     AND json_extract(p.data,'$.tool')='question'
     AND json_extract(p.data,'$.state.status') != 'completed'
  ) AS pending_q
FROM session s
WHERE (s.time_archived IS NULL OR s.time_archived = 0)
ORDER BY s.time_updated DESC;
"""

STATE_COLOR = {
    "running": "#2fd06f",
    "idle": "#f5b13d",
    "waiting": "#ff5a4e",
    "off": "#5a5e6b",
}
STATE_GLYPH = {
    "running": "RUNNING",
    "idle": "IDLE",
    "waiting": "WAITING",
    "off": "OFF",
}


def now_ms() -> int:
    return int(datetime.now().timestamp() * 1000)


def derive_state(pending_q: int, last_part_upd_ms) -> str:
    if pending_q > 0:
        return "waiting"
    if last_part_upd_ms is not None and now_ms() - last_part_upd_ms < RUN_WINDOW_MS:
        return "running"
    return "idle"


def load_projects() -> list[dict]:
    data = json.loads((PLUGIN_DIR / "projects.json").read_text())
    return [
        {"alias": p["alias"], "path": p["path"]}
        for p in data.get("projects", [])
    ]


def attribute_to_project(directory: str | None, projects: list[dict]):
    norm = str(directory or "").replace("\\", "/").rstrip("/")
    best, best_len = None, -1
    for p in projects:
        np = str(p["path"]).replace("\\", "/").rstrip("/")
        if norm == np or norm.startswith(np + "/"):
            if len(np) > best_len:
                best, best_len = p, len(np)
    return best


def live_states() -> dict:
    conn = sqlite3.connect(str(DB_PATH))
    try:
        rows = conn.execute(QUERY).fetchall()
    finally:
        conn.close()

    by_dir: dict[str, tuple] = {}
    for row in rows:
        sid, directory, title, upd, last_part_upd, pending_q = row
        d = directory or ""
        cur = by_dir.get(d)
        if cur is None or (upd or 0) > (cur[3] or 0):
            by_dir[d] = (sid, d, title, upd, last_part_upd, pending_q)

    states: dict[str, dict] = {}
    for sid, d, title, upd, last_part_upd, pending_q in by_dir.values():
        states[d] = {
            "state": derive_state(pending_q, last_part_upd),
            "sessionId": sid,
            "title": title,
            "directory": d,
        }
    return states


def read_current_page_buttons() -> list[dict]:
    client = McpStdioClient(["streamdeck-mcp"])
    try:
        client.request(
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "live-screen", "version": "1.0"},
            },
        )
        client.notify("notifications/initialized")

        profiles_raw = client.call_tool("streamdeck_read_profiles")
        profiles = profiles_raw
        if isinstance(profiles_raw, dict) and "raw" in profiles_raw:
            profiles = json.loads(profiles_raw["raw"])

        result = []
        for p in profiles:
            device = json.dumps(p.get("device", {}))
            if "20GAI9901" not in device:
                continue
            for page in p.get("pages", []):
                if not page.get("is_current"):
                    continue
                page_data = client.call_tool(
                    "streamdeck_read_page",
                    {"profile_id": p["profile_id"], "directory_id": page["directory_id"]},
                )
                result.append(
                    {
                        "profile": p["name"],
                        "page": page["page_uuid"],
                        "buttons": page_data.get("buttons", []),
                    }
                )
        return result
    finally:
        client.close()


def render(projects, states, page_info) -> None:
    if not page_info:
        print("No current page found for the deck (20GAI9901).")
        return

    info = page_info[0]
    buttons = info["buttons"]
    print(
        f"Profile: {info['profile']}  ·  page: {info['page']}\n"
        f"Projects: {[p['alias'] for p in projects]}"
    )

    rows, cols = 2, 3

    def key_state_for(i: int) -> dict:
        b = next((x for x in buttons if x.get("key") == i), None)
        if b is None:
            return {"state": "off", "label": "empty"}
        action_uuid = (b.get("raw") or {}).get("UUID", "")
        if "opendeck.alert" in action_uuid:
            waiting = [s for s in states.values() if s["state"] == "waiting"]
            return {
                "state": "waiting" if waiting else "idle",
                "label": f"Needs You ({len(waiting)})",
            }
        if i < len(projects):
            p = projects[i]
            st = states.get(p["path"].replace("\\", "/").rstrip("/"))
            if st:
                return {"state": st["state"], "label": p["alias"]}
        return {"state": "off", "label": "add project" if i >= len(projects) else p["alias"]}

    grid = []
    for r in range(rows):
        cells = []
        for c in range(cols):
            i = r * cols + c
            ks = key_state_for(i)
            cells.append(f"{STATE_GLYPH[ks['state']]:<8} {ks['label']} {STATE_COLOR[ks['state']]}")
        grid.append(cells)

    sep_mid = "├" + "┼".join(["─" * 26 for _ in range(cols)]) + "┤"
    for idx, cells in enumerate(grid):
        if idx == 0:
            print("┌" + "┬".join(["─" * 26 for _ in range(cols)]) + "┐")
        else:
            print(sep_mid)
        print("│" + "│".join([f" {c:<26}" for c in cells]) + "│")
    print("└" + "┴".join(["─" * 26 for _ in range(cols)]) + "┘")
    print()
    print("States: running=green, idle=amber, waiting=red, off=gray")


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    projects = load_projects()
    states = live_states()
    page_info = read_current_page_buttons()
    render(projects, states, page_info)
    return 0


if __name__ == "__main__":
    sys.exit(main())
