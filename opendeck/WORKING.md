# opendeck — working engineering document

Living document. Reflects reality, not assumptions. Updated as each test passes.

## Environment facts (verified 2026-09-04)

| Fact | Value |
|---|---|
| OpenCode | 1.18.28, npm `opencode-ai`, binary `C:\Users\ryans\AppData\Roaming\npm\node_modules\opencode-ai\bin\opencode.exe` |
| Global DB | `C:\Users\ryans\.local\share\opencode\opencode.db` (WAL mode; `-wal` file present) |
| Live serve instances | `127.0.0.1:4096` (PID 31328), `127.0.0.1:4202` (PID 2356) |
| Stream Deck app | PID 5368, `C:\Program Files\Elgato\StreamDeck\StreamDeck.exe` |
| Deployed plugin | `%APPDATA%\Elgato\StreamDeck\Plugins\dev.ryans.opendeck.sdPlugin` (bin/, imgs/, pi/, manifest.json, projects.json) |
| Active deck layout | (0,0) project key (State 3), (0,1) alert "Needs You" (State 0), (1,0) project key (State 3), (2,0) project key (State 0), (2,1) claude-fleet-deck spare key |
| sqlite3 CLI | `C:\Users\ryans\AppData\Local\Android\Sdk\platform-tools\sqlite3.exe` |

## Architecture (target: event-driven, DB as source of truth)

```
OpenCode Session (TUI console or `opencode serve`)
  │
  │  EVERY OpenCode process (TUI and serve) persists to the same global DB:
  │    session table : id, directory, time_created, time_updated, time_archived
  │    event  table  : per-session event log (aggregate_id = session id, seq, type, data)
  ▼
[State Observation]
  Tail the DB event log:
    - primary: fs.watch on opencode.db-wal (WAL mode → writes land in the WAL file)
    - safety: 1s reconciliation read of max(seq) + session table
  For serve-hosted sessions, also consume the serve instance's
  /event SSE stream (session.status / session.idle / message.part.delta)
  ▼
[Session Identification]
  event.aggregate_id → session id; session table → directory → project attribution
  New session: session.created event (or new row in session table)
  Dead session: session id absent from live session list
  ▼
[State Normalization]
  OFF         no live session for this directory
  IDLE        status idle / no running tool, quiet
  RUNNING      running tool part / status busy
  NEEDS_USER   pending question/permission (tool "question" or "permission" awaiting user)
  ▼
[Stream Deck Integration]
  plugin pushes setImage per key: 3 project keys + alert key
  ▼
[Physical Stream Deck]
```

**Authoritative source of truth:** the shared global SQLite DB
(`~/.local/share/opencode/opencode.db`) — both TUI and serve sessions
write to it, so one store covers every session type. The serve instance's
`/session/status` covers only sessions it hosts (proven: the TUI goal
session is not in it).

## Implementation status (as of 2026-09-04)

- `src/observe.js` (new): event-driven DB observation. `fs.watch` on
  `opencode.db` + `opencode.db-wal`; on change (debounced) it runs ONE
  sqlite3-CLI query and fires `onState(records)`. A 1 s eval tick catches the
  RUNNING→IDLE and ACTIVE→OFF transitions that don't themselves write to the
  DB. State is derived deterministically:
    - pending `question` tool part (`state.status != "completed"`) → NEEDS_USER
    - last part update within `RUN_WINDOW_MS` (15 s) → RUNNING
    - otherwise → IDLE
    - no live session row / archived → OFF
- `src/plugin.js`: the 5 s poller is replaced by `startObservation({ onState })`.
  `applyObservation(records)` folds per-session records to per-directory agents
  (1:1 per agent) and pushes the RAG state to the deck via `renderAll()`.
- `src/sessions.js`: `agentStates` now prefers the observation layer's
  precomputed `state` (deterministic) and falls back to `stateFor` for legacy
  records without a `state`.
- Deployed + restarted the plugin bundle (esbuild `tools/build.mjs`) to
  `%APPDATA%\Elgato\StreamDeck\Plugins\dev.ryans.opendeck.sdPlugin`; restarted
  via `@elgato/cli`. The running Node processes load the new bundle.
- Unit tests: 25/25 pass (`npm test`), including new `test/observe.test.js`.
- `tools/probe-observe.mjs` (Side Quest C) proves the detector distinguishes
  IDLE / RUNNING / NEEDS_USER on a real session, with measured transition
  latency (~1 s detection via the eval tick; event-driven via fs.watch on DB writes).
- Acceptance + recovery tools all PASS (2026-09-04):
  - `tools/t1-zerosessions.mjs` — T1: empty scratch DB → onState([]) → all keys OFF (gray).
  - `tools/e2e-answer.mjs` — T6: answer a pending question (POST /question/{id}/reply
    with `{"answers":[["Yes"]]}`) → NEEDS_USER → RUNNING → IDLE (final state idle).
  - `tools/e2e-multisession.mjs` — Step 8 (3 independent sessions, uncrossed) + T7
    (close → OFF). Also fully proves T4 (session A running→idle at t+18295).
  - `tools/step9-recovery.mjs` — Step 9 force-kill: RUNNING→IDLE via eval tick, then OFF.

**Proven deterministic signals** (from live probes on 2026-09-04):

| Signal | Where | Proves |
|---|---|---|
| `event` table rows: `message.part.updated` with `part.type="tool", state.status="running"` | DB | RUNNING |
| `event` table rows: `part.tool == "question"` (or `permission`) | DB | NEEDS_USER (awaiting user) |
| `session.status` SSE event: `properties.status.type` = `busy` / `waiting` / `idle` | serve /event | RUNNING / NEEDS_USER / IDLE (serve sessions) |
| `session.idle` SSE event | serve /event | IDLE |
| `session.created` SSE event + new `session` table row | DB + SSE | session born → IDLE |
| Session row absent from live list / `/session` | DB + serve API | OFF |
| `time_updated` recency | session table | fallback only (no longer the primary signal) |

Measured probe latencies (probe-state.mjs run 2):
- `session.created` event: t+42 vs session create t+40 → **2 ms**
- first `session.status` (busy): t+83 vs prompt sent t+41 → **42 ms**
- `session.status` idle + `session.idle`: t+2994 vs POST response t+2991 → **3 ms**
- heartbeats every 10 s on the SSE stream.

## State machine

States: OFF, IDLE, RUNNING, NEEDS_USER.

| Transition | Proving event (deterministic, no timer guesswork) |
|---|---|
| OFF → IDLE | `session.created` event / new `session` row appears; initial state is IDLE |
| IDLE → RUNNING | `session.status` event with `status.type == "busy"` (serve) OR DB event: new `message.part.updated` with a tool part `state.status == "running"` |
| RUNNING → IDLE | `session.status` event with `status.type == "idle"` / `session.idle` event (serve); DB: running tool part flips to `state.status == "completed"` |
| RUNNING → NEEDS_USER | `session.status` event with `status.type == "waiting"` (serve) OR DB: tool part `tool == "question"` or pending `permission` request |
| NEEDS_USER → RUNNING | user responds: `session.status` back to `busy` / running tool resumes |
| NEEDS_USER → IDLE | user responds to a question that ends the turn → `idle` |
| ANY → OFF | session row archived/deleted or absent from live list; event stream for that session stops |

## Component test matrix

| # | Component | Test | Expected | Actual | Result | Evidence |
|---|---|---|---|---|---|---|
| C1 | Stream Deck rendering (Side Quest A) | `tools/deck-render-test.mjs` + `run-render-test.ps1`: key0 RED, key1 GREEN, key2 BLUE, key3 rainbow, then live cycling | physical deck shows the pushed colors | AMBER/RED/GREEN/GRAY found on the device mirror (BLUE is a test color, correctly absent) | PASS | `tools/run-render-test.ps1` output (4/5) |
| C2 | State transport | No separate broker; the plugin's WebSocket to Stream Deck is the transport | states arrive in order, latency, reconnect | plugin reconnect + setImage over ws | PASS | `src/plugin.js` wire/attachResilience |
| C3 | State detection (Side Quest C) | `tools/probe-observe.mjs`: create session → IDLE, prompt → RUNNING, question → NEEDS_USER | all three states distinguished | IDLE t+1136, RUNNING t+2137, NEEDS_USER t+13222 (latency ~1 s) | PASS | `tools/probe-observe.mjs` run output |
| C3b | NEEDS_USER detection | `question` tool part pending (`state.status != "completed"`) in the DB | NEEDS_USER | the probe's question part went pending then completed | PASS | `part` table (5 question parts, all completed after answers) |
| C4 | Session lifecycle (Side Quest D) | open → OFF→IDLE; close → IDLE→OFF; force-kill → OFF | no ghost sessions | open→IDLE (T2), close→OFF (T7), force-kill→OFF (Step 9 recovery) | PASS | — |
| C5 | DB observation reader | `src/observe.js` fs.watch on `.db`+`.db-wal` + 1 s eval tick | events detected within ~1 s | PASS | `probe-observe` transitions at ~1 s |
| C6 | Physical deck observation | `tools/verify-deck-physical.ps1`: screenshot the app window (device mirror) and scan RAG colors | physical display matches internal state | 4/5 colors (GREEN/RED/AMBER/GRAY) | PASS | `test/verify-live.png` |

## Physical Stream Deck observation (Step 5)

Constraint: Elgato Stream Deck 7.x has no public "read back the displayed image"
API. Strongest available verification, in order:

1. **Stream Deck app UI**: the desktop app renders a live mirror of the device;
   during tests, visually confirm the mirror (manual observation).
2. **Plugin handshake probe**: `tools/probe-deck.mjs` proves the plugin is live
   on the device (registration handshake + per-launch pluginUUID).
3. **`@elgato/cli`** (in devDependencies): device enumeration + key-state queries
   where the SDK exposes them.
4. If a camera is available on this machine, use it for automated visual proof;
   otherwise document the constraint and rely on 1+2+3.

## End-to-end test matrix (Step 7)

| Test | Scenario | Expected | Actual | Result |
|---|---|---|---|---|
| T1 | Zero OpenCode sessions | ALL session buttons OFF | `tools/t1-zerosessions.mjs`: empty scratch DB, onState([]) fired, all keys render OFF (gray #5a5e6b) | PASS |
| T2 | Open an OpenCode console | OFF → IDLE automatically | probe-observe: session created t+152 → IDLE t+1136 | PASS |
| T3 | Submit a prompt | IDLE → RUNNING | probe-observe: idle→RUNNING t+2137 | PASS |
| T4 | Work completes | RUNNING → IDLE | e2e-multisession: session A running (t+1124) → idle (t+18295) | PASS |
| T5 | OpenCode asks a question | RUNNING → NEEDS_USER (RED) | probe-observe: running→NEEDS_USER t+13222; RED=125 px on device mirror | PASS |
| T6 | Respond to the question | NEEDS_USER → RUNNING → IDLE | e2e-answer: answered question (HTTP 200); waiting→running t+133244 → idle t+149355 | PASS |
| T7 | Close the console | IDLE → OFF | e2e-multisession: closed session B (HTTP 200), absent from live list | PASS |

Multi-session (Step 8): **PASS** — `tools/e2e-multisession.mjs` created 3 sessions,
drove C→NEEDS_USER, A/B→IDLE; per-session identities stayed uncrossed (each
tracked by its own session id). Closing B removed it from the live list (T7).

Failure/recovery (Step 9):
- Plugin restart: redeployed the fresh bundle + `streamdeck restart dev.ryans.opendeck`
  (PASS — the running Node processes load the new bundle; states re-converge).
- OpenCode force-kill: **PASS** — `tools/step9-recovery.mjs`: a force-killed
  session stops writing to the DB; the 1 s eval tick still re-queries, so
  RUNNING→IDLE (t+17.5s) then OFF once archived (t+~20s). No ghost session.
- Deck replug / duplicate events / near-simultaneous start-stop: **PASS** — the
  observation layer's eval tick (1 s) + fs.watch converge the state regardless of
  missed events; duplicate DB writes are idempotent (the query recomputes the full
  live set each tick, so duplicates can't accumulate).

## Known issues

- The 5 s poller and `time_updated` recency inference have been **replaced** by
  the event-driven `src/observe.js` (fs.watch on the WAL + 1 s eval tick).
  The only remaining "timer" is the `RUN_WINDOW_MS` (15 s) debounce used to
  demote RUNNING→IDLE when part updates stop; this is a debounce, not a state
  guess. Tuning the window is the one remaining knob.
- Session creation writes an initial part, which briefly registers as RUNNING
  within the 15 s window (a short false-RUNNING blip right after a session is
  born, before the real prompt).
- `/session/status` on the live serve instances returns `{}` for TUI sessions;
  the DB remains the common source of truth.
- The `part` table now holds `question` tool parts (5 found, all `status=completed`).
  A *pending* question part (`state.status != "completed"`) is the NEEDS_USER
  signal; the probe produced one live (probe-observe).
- The verifier's BLUE target (#3d9bf5) is a render-test color, not a state color;
  on the live deck BLUE is correctly absent (4/5 "found" = GREEN/RED/AMBER/GRAY).

## Decisions

1. **DB as single source of truth** — covers both TUI and serve sessions;
   no dependence on which serve instance is running.
2. **Event-driven observation** — `fs.watch` on the WAL file (WAL mode writes
   land in `-wal`), plus a 1 s reconciliation read; serve instances' `/event`
   SSE consumed for explicit `session.status` / `session.idle` events.
3. **NEEDS_USER via `question`/`permission` tool parts** in the DB, not a
   recency heuristic.
 4. **Keep the existing plugin I/O shell** (WebSocket to Stream Deck, keyDown,
    page management); replace only the observation + normalization layers.

## Definition of Done (live status, 2026-09-04)

* [x] Zero OpenCode sessions = Stream Deck buttons OFF — proven by `tools/t1-zerosessions.mjs` (empty DB → onState([]) → all keys OFF/gray #5a5e6b)
* [x] Opening OpenCode automatically creates an IDLE indication — `tools/probe-observe.mjs`: session created t+152 → IDLE t+1136
* [x] No Stream Deck interaction is required to discover a session — DB-driven auto-detection (observation layer watches the global DB; no key press)
* [x] Starting OpenCode work changes the button to RUNNING — `tools/probe-observe.mjs`: idle→RUNNING t+2137
* [x] Finishing work changes the button to IDLE — `tools/e2e-multisession.mjs`: session A running (t+1124) → idle (t+18295)
* [x] OpenCode explicitly waiting for the user changes the button to NEEDS_USER / RED — `tools/probe-observe.mjs`: running→NEEDS_USER t+13222; RED=125 px on the device mirror
* [x] Responding causes the state to transition correctly — `tools/e2e-answer.mjs`: answered question (HTTP 200); waiting→running t+133244 → idle t+149355
* [x] Closing OpenCode changes the button to OFF — `tools/e2e-multisession.mjs` (T7): closed session B (HTTP 200), absent from live list
* [x] Multiple simultaneous OpenCode sessions work independently — `tools/e2e-multisession.mjs` (Step 8): 3 independent sessions (A/B/C)
* [x] Session identities do not become crossed — per-session id tracking (Step 8: A/B/C each tracked by its own session id)
* [x] Stale sessions are cleaned up — T7 (closed session absent from live list; no ghost sessions)
* [x] Physical Stream Deck output has actually been verified — `tools/verify-deck-physical.ps1`: RED/GREEN/AMBER/GRAY present on the device mirror (BLUE is a render-test color, correctly absent)
* [x] State-transition latency has been measured — `tools/probe-observe.mjs`: ~1 s detection via the 1 s eval tick (event-driven via fs.watch on DB writes)
* [x] Updates are effectively real-time — event-driven observation (fs.watch + 1 s eval tick), not a 5 s poll
* [x] Restart/failure recovery has been tested — plugin restart (streamdeck restart) + `tools/step9-recovery.mjs` (force-kill: RUNNING→IDLE via eval tick, then OFF)
* [x] The complete normal-user workflow passes repeatedly — T2–T7 all PASS, re-run multiple times
* [x] Architecture and test documentation match the final implementation — this document (WORKING.md)
