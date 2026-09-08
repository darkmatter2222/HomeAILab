# OpenCode Deck — System Architecture

Authoritative, end-to-end architecture of the OpenCode ↔ Stream Deck
monitoring and control system. This document is the reference for the
acceptance tests in this goal.

## Component map (data path)

```
OpenCode Process / CLI
│   TUI sessions (`opencode --model ... --auto`) and `opencode serve`
│   instances (127.0.0.1:4096, :4202).
↓
OpenCode State Observation
│   Every OpenCode process persists to ONE shared store:
│     ~/.local/share/opencode/opencode.db  (WAL mode)
│     tables: session, part, event, message...
↓
Session Discovery
│   src/observe.js — event-driven:
│     • fs.watch on opencode.db and opencode.db-wal (200 ms debounce)
│     • 1 s eval tick (re-runs the single sqlite3 query) to catch the two
│       transitions that do NOT write to the DB: RUNNING→IDLE (last part
│       update ages past the 15 s window) and ACTIVE→OFF (session archived)
↓
Session Identity
│   event.aggregate_id → session id; session table → directory → project
│   alias (opendeck/projects.json: alias/path/bat). Unmatched directories
│   are minted into projects.auto.json.
↓
State Detection
│   src/observe.js — detects the raw signals inside OpenCode:
│     • pending `question` tool part (state.status != "completed")
│     • last part update within 15 s (RUN_WINDOW_MS)
│     • no live session row (archived/absent)
↓
State Normalization
│   src/observe.js deriveState (deterministic, no timer guessing):
│     • pending question → WAITING (red)
│     • part update within 15 s → RUNNING (green)
│     • otherwise → IDLE (amber)
│     • no live session row → OFF (gray)
│   For serve-hosted sessions the serve instance's /event SSE stream
│   (session.status busy/waiting/idle, session.idle) is a second, explicit
│   authoritative signal (the DB is still the common store).
↓
Server / Broker / API
│   There is no separate broker: the plugin's WebSocket to the Stream Deck
│   host (ws://127.0.0.1:<port>) is the transport. The MCPN API
│   (streamdeck-mcp) is the independent observation layer used by the
│   acceptance harness:
│     • profile mode (streamdeck-mcp): app-side saved profile/page/button
│       state (streamdeck_read_profiles / streamdeck_read_page)
│     • USB mode (streamdeck-mcp-usb): live on-screen key state read over
│       HID (streamdeck_list_devices / streamdeck_connect / streamdeck_info
│       / streamdeck_list_pages / streamdeck_get_button)
↓
Stream Deck State Manager
│   src/plugin.js applyObservation(): folds per-session records into
│   per-working-directory agents (1:1), writes auto-projects, calls
│   renderAll() → setKeyImage() (setImage over WebSocket, SVG data URI).
↓
Stream Deck Renderer
│   src/keyart.js — pure 144x144 SVG renderers, RAG colors:
│   running #2fd06f (green), idle #f5b13d (amber),
│   waiting #ff5a4e (red), off #5a5e6b (gray).
↓
Physical Stream Deck
│   Elgato Stream Deck Mini (2x3 = 6 keys, current page "Default Profile").
│   The Stream Deck app renders a live mirror of the device; the physical
│   display is validated through the app mirror + USB readback
│   (streamdeck-mcp-usb streamdeck_get_button).
```

## Control path (button press)

```
Physical Stream Deck Button Press
↓
Button Event
│   keyDown event over the plugin WebSocket (opaque context hash per key).
↓
Session Lookup
│   contextMap: context → { action, slot } → project alias →
│   state.live[alias].sessionId (set by applyObservation).
↓
Window / Terminal Identification
│   The launcher opens `wt -w new -d <path> cmd /k "title opencode:<alias>
│   opencode & <bat>"` so the tab title carries a stable marker
│   (`opencode:<alias>`). focusSession EnumWindows-scans for the marker and
│   raises that exact terminal (ShowWindow + SetForegroundWindow); fallback
│   activates Windows Terminal if no titled window exists.
↓
Activate / Focus Correct OpenCode CLI
│   Only when a live session exists for that key. OFF key (no session) →
│   press does nothing.
```

## Authoritative sources (per requirement)

| Requirement | Authoritative source |
|---|---|
| Session existence | global `opencode.db` session table (`time_archived IS NULL OR = 0`) |
| Session identity | `session.id` (+ `event.aggregate_id`), `session.directory` → project alias via projects.json |
| Session state | DB-derived: pending question → WAITING; part update < 15 s → RUNNING; else IDLE; no live row → OFF. Serve sessions additionally: explicit `session.status` (busy/waiting/idle) SSE events |
| Terminal / window identity | Windows Terminal tab title marker `opencode:<alias>` (set at launch); EnumWindows match |
| Stream Deck button assignment | Stream Deck app profile layout: key position → `action_uuid` (dev.ryans.opendeck.project / .alert) → slot → project alias (MCPN `streamdeck_read_page` returns this mapping) |

## State machine (deterministic)

States: OFF, IDLE, RUNNING, WAITING (NEEDS USER).

| Transition | What actually happens inside OpenCode | Observable signal | Detected by | Transmission | Time to deck | On-screen result |
|---|---|---|---|---|---|---|
| OFF → IDLE | User launches `opencode` (or the launch key double-tap creates a second session) | New `session` row in the DB (+ `session.created` event) | observe.js fs.watch on WAL | DB write → 200 ms debounce → onState → setImage | ~0.2 s | Key: IDLE (amber) |
| IDLE → RUNNING | Prompt submitted; generation/tool execution begins | `message.part.updated` with tool part `state.status="running"` (DB event); serve: `session.status` SSE `busy` | observe.js watcher; SSE | DB/SSE → onState → setImage | ~0.2 s (DB) / immediate (SSE) | Key: RUNNING (green, breathing) |
| RUNNING → IDLE | Generation/tool completes | Last `part.time_updated` older than 15 s; or `session.status` idle / `session.idle` SSE | 1 s eval tick | eval tick → onState → setImage | ≤ 1 s | Key: IDLE (amber) |
| RUNNING → WAITING | OpenCode asks a question / requests permission | `part` row `tool="question"`, `state.status != "completed"`; serve: `session.status` SSE `waiting` | DB watcher (part write) | DB → onState → setImage | ~0.2 s | Key: WAITING (red, breathing) |
| WAITING → RUNNING | User answers the question | Question part completes; running parts resume | DB watcher | same | ~0.2 s | Key back to RUNNING (green) |
| WAITING → IDLE | Answer ends the turn | No pending question; `session.idle` | eval tick / SSE | same | ≤ 1 s | Key: IDLE (amber) |
| ANY → OFF | Terminal closed / process killed / session archived | Session row archived (`time_archived` set) or absent from live list | 1 s eval tick | same | ≤ 1 s | Key: OFF (gray, blank) |

No state may be inferred from arbitrary timing when an authoritative signal
exists. The only timing element is the 15 s `RUN_WINDOW_MS` debounce that
demotes RUNNING→IDLE when part updates stop — a debounce, not a guess.

## Session-to-button identity model

```
opencode process (PID, per working dir)
  ↔ session id (DB session.id)
  ↔ working directory (session.directory)
  ↔ project alias (projects.json path match)
  ↔ Stream Deck key (page key position, action_uuid dev.ryans.opendeck.project)
```

The mapping is maintained per session id, so identities survive state
changes: a RUNNING key always focuses the terminal tab whose title contains
`opencode:<alias>` for the alias of its directory. Crossed identities are
impossible because the lookup chain is key slot → alias → live[alias].
sessionId → marker.

## Button press semantics (the critical defect, fixed)

- The `project` action is defined with a **single state** in the manifest
  (previously 4 states, which the Elgato app cycles on long-press). With
  one state there is nothing to cycle.
- Pressing a project key:
  - Live session exists → `focusSession` raises the matching terminal. State
    does NOT change.
  - No live session (OFF) → the press does nothing (no launch, no state
    change, no fake session).
  - Double-tap → launches a second concurrent session (a genuine OpenCode
    state change: a new session is born → OFF → IDLE).
- Pressing the "launch" key: if that slot has a live session → focus it;
  otherwise launch the project (genuine new-session creation).
- Pressing the "Needs You" alert key: no state change; it is a display
  aggregate.

## Interfaces (every boundary)

| Boundary | Protocol |
|---|---|
| OpenCode → global DB | SQLite WAL writes (session/part/event tables) |
| observe.js → plugin | `onState(records)` callback, fired by fs.watch (debounced) + 1 s tick |
| plugin → Stream Deck host | WebSocket JSON-RPC-ish events: `registerPlugin`, `setImage`, `keyDown`, `willAppear`, `didReceiveSettings` |
| Stream Deck app → physical device | HID/USB (device mirror in the app) |
| harness → device state | MCPN profile mode (`streamdeck_read_page` → per-key `state` index) and USB mode (`streamdeck_get_button` → live on-screen state) |
| focus.js → Windows Terminal | EnumWindows title-marker scan (`opencode:<alias>`) → ShowWindow/SetForegroundWindow |

## Acceptance harness

`streamdeck/acceptance.py` drives and validates the full TC-001..TC-054
matrix: launches real OpenCode sessions, submits real prompts, answers real
questions, closes/kills sessions, reads back the physical deck state via the
MCPN API, and records PASS/FAIL with timestamps and latency. See
`streamdeck/README.md` for usage.
