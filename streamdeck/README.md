# Stream Deck state fetcher

## Component test matrix (goal artifact 4)

Each component of the OpenCode <-> Stream Deck system has a reproducible
test; evidence for every row is in the acceptance run logs.

| Component | Test | Evidence |
|---|---|---|
| DB state observation (`opendeck/src/observe.js`) | `opendeck/test/observe.test.js`, `observe.sanity.mjs` | 25/25 unit tests pass (`cd opendeck; npm test`) |
| Key-art renderer (`opendeck/src/keyart.js`) | `opendeck/test/render.test.js` | Unit tests pass (same `npm test` run) |
| Session discovery | `opendeck/test/sessions.test.js` | Unit tests pass (same `npm test` run) |
| MCPN USB readback | `fetch_state.py` (streamdeck-mcp-usb) | acceptance log `deck_state` fields (TC-040/041) |
| MCPN profile readback | `read_active_page.py` (streamdeck-mcp) | acceptance log `profile_key_map` (TC-040/041) |
| Button press simulation | `acceptance.press_key` (plugin WebSocket keyDown, port 28196) | acceptance log `press.pressed=True` (TC-030..034, TC-011) |
| Focus / window identification | `find-marked-window.ps1` / `fgtitle.ps1` (EnumWindows marker scan) | acceptance log `focus.matched=True` (TC-021/031/032/033/034) |
| Physical display validation | `opendeck/tools/verify-deck-physical.ps1` (app-mirror color scan) | acceptance log `physical.color_found=True` (21 entries across idle/running/waiting/off) |
| End-to-end acceptance | `acceptance.py` + `batch.py` | `acceptance-report.md`: 30/30 PASS |

## Scripts

- `fetch_state.py` — USB-mode (`streamdeck-mcp-usb`): live device info +
  per-key saved state (device grid, brightness, pages, per-key config).
- `read_active_page.py` — profile-mode (`streamdeck-mcp`): reads the Elgato
  app's active profile current page + per-key native actions (saved state).
- `live_screen.py` — the single "what's on the screen right now" script.
  Mirrors the OpenCode Deck plugin's observation layer: reads
  `~/.local/share/opencode/opencode.db` (sqlite3) with the plugin's exact
  state machine (waiting/red = open question, running/green = part updated
  in last 15s, idle/amber = quiet session, off/gray = no session for that
  project), maps sessions to the `projects.json` projects (homeai, ryans),
  and renders the actual on-screen state as ASCII art. No screenshot.

Pulls the live on-screen state of an Elgato Stream Deck through the
[streamdeck-mcp](https://github.com/verygoodplugins/streamdeck-mcp) MCP
server (Very Good Plugins) in USB-direct mode (`streamdeck-mcp-usb`).
No screenshot of the Stream Deck software is taken; state is read over
USB/HID and the MCP tool API.

## Requirements

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) for `uvx` (installs the server on first
  run, cached afterward)
- `hid` Python package + native `hidapi.dll` (Windows): get
  [hidapi-win.zip](https://github.com/libusb/hidapi/releases) from the
  hidapi release page and place `x64/hidapi.dll` next to the Python
  executable (or next to the MCP server .exe) so `ctypes` can load it.

## Usage

```
python streamdeck/fetch_state.py
python streamdeck/fetch_state.py --serial <serial>
```

`--serial` selects a specific deck when several are attached (get the serials
from the `devices` section of the output).

## Output

JSON document with:

- `devices` — attached decks: serial, type, key count (`streamdeck_list_devices`)
- `connect` — connect result text (`streamdeck_connect`)
- `deck` — model, key grid, firmware, current page, brightness
  (`streamdeck_info`)
- `pages` — page list + current page (`streamdeck_list_pages`)
- `screen.keys[]` — per-key on-screen state: label text, image path,
  colors, action (`streamdeck_get_button` per key)

## Note on `streamdeck_list_devices`

The PyPI build (0.3.0) predates the `streamdeck_list_devices` tool (it
exists in newer main-branch builds). When the server answers "Unknown tool",
the client falls back to deriving the device entry from `streamdeck_info`.

## Custom server command

The server is launched via `uvx --from streamdeck-mcp streamdeck-mcp-usb`.
If you installed the package with pip instead, override with:

```
pip install streamdeck-mcp
set STREAMDECK_MCP_CMD=streamdeck-mcp-usb
python streamdeck/fetch_state.py
```
