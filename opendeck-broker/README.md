# opendeck-broker

Local broker for the OpenCode-dedicated Elgato Stream Deck Mini. This is
**option A** from `docs/streamdeck-opencode-research.md`: one Python process owns
the six slots, receives actual OpenCode state, and routes presses to a Windows
focus adapter. The Mini is controlled **directly over HID** after the individual
device is disabled in the Elgato app (`Preferences > Devices > Enabled`), so the
broker never fights Elgato for the same device.

The prior Node/TS Elgato-plugin implementation lives in `../opendeck/` (option B)
and is kept as the supported alternative; do not run both against the same Mini.

## Behavior contract

| Slot shows | Meaning | Press |
|---|---|---|
| black, no text | no live TUI assigned | nothing |
| amber + `IDLE` | live, ready for a prompt | focus that instance |
| green + `RUN` | busy / generating / tool / auto-retry | focus that instance |
| red + `INPUT` | unresolved permission or structured question | focus (do not answer) |
| amber + `?` (`UNKNOWN`) | telemetry not trustworthy / bridge down | focus |

Six slots, row-major: top-left..top-right, then bottom-left..bottom-right.
An instance keeps its slot until it closes (no compaction); a 7th launch runs
but gets no button (overflow), never evicting a live occupant.

**Window identity = unique launch token.** A press focuses by a per-launch
marker (`opencode:<alias>-<launchid>`), not by project title or PID. Two TUIs in
the same directory share an alias but get distinct markers, so focus is
unambiguous (research section 10: "Launch token plus validated window and
terminal binding"). The launcher sets the window title to this marker; focus
scans for it and verifies the resulting foreground window.

## Package layout

```
opendeck_broker/
  model.py        Instance/Status/DisplayAppearance + the pure reducer
  registry.py     six-slot registry: generations, epoch/sequence, stale rejection
  broker.py       wires registry + device + focus; render + press loop
  images.py       renders one key image (color + identity baked in) via Pillow
  config.py       env-driven config + loopback token
  api.py          loopback REST API + /v1/deck SSE push
  lock.py         per-user single-instance lock (named mutex / lockfile)
  device/base.py  DeviceAdapter interface (one device owner)
  device/mock.py  in-memory device for headless tests
  device/hid_mini.py  direct-HID Mini adapter (python-elgato-streamdeck or raw hid)
  focus/windows.py    EnumWindows resolve + SetForegroundWindow + verify
  opencode/observe.py global opencode.db reader -> per-directory state facts
  opencode/adapter.py binds launches to the broker, pushes observed state
  main.py         CLI entrypoint (run the broker loop)
tools/
  probe_device.py  PHYSICAL: open Mini, 6 black, 6 numbered, 6 key events
  probe_focus.py   PHYSICAL: focus a terminal, verify foreground
  selftest.py      SIMULATED: headless end-to-end with a mock device
  demo_live.py     LIVE: read the real OpenCode DB, render the frame (mock device)
tests/
  test_reducer.py / test_registry.py / test_protocol.py
  test_focus.py / test_observe.py / test_e2e_mock.py / test_api.py
```

## Install + test

```
cd opendeck-broker
pip install -r requirements.txt
python -m pytest tests -q        # headless (no Mini required)
python tools/selftest.py         # simulated end-to-end demo
python tools/demo_live.py        # render the real six-slot frame from the live DB
```

`requirements.txt` needs `hidapi` (the `hid` Python binding, which on Windows also
needs `hidapi.dll`) and `Pillow`. `elgato-streamdeck` is optional and preferred:
it pins the Mini image/key-report protocol; without it the raw-`hid` fallback is
used and must be confirmed by `probe_device.py`.

## Run the broker

```
# smoke test, no hardware (mock device, one tick):
python -m opendeck_broker.main --mock --once

# real: Mini attached + disabled in Elgato, then:
python -m opendeck_broker.main
```

At logon it: acquires the single-instance lock, connects the Mini, uploads six
black keys, then on each tick observes the global OpenCode DB, re-renders changed
slots, and processes any queued key presses.

## Endpoints (loopback, `X-OpenDeck-Token` header)

| Endpoint | Purpose |
|---|---|
| `POST /v1/instances/register` | register a live TUI launch, get its slot |
| `PUT /v1/instances/{id}/snapshot` | push normalized state (newer producer seq) |
| `POST /v1/instances/{id}/heartbeat` | renew presence; returns broker epoch |
| `DELETE /v1/instances/{id}` | detach (clears the slot) |
| `GET /v1/display` | desired six-slot frame |
| `GET /v1/deck` | SSE push stream (full snapshots / updates) |
| `POST /v1/focus` | focus a known instance (+ expected generation) |
| `GET /v1/diagnostics` | frame, overflow, live instances, focus log |

## Auto-start (research sections 4, 8)

Run at user logon with restart-on-failure, in the interactive user session:

```
powershell -ExecutionPolicy Bypass -File tools\install-autostart.ps1        # install
powershell -ExecutionPolicy Bypass -File tools\install-autostart.ps1 -Remove # uninstall
```

Registers a Task Scheduler task (`OpenDeckBroker`, logon trigger, interactive
user, restart-on-failure) that runs a small supervisor loop (`tools/
opendeck-broker-supervisor.bat`, generated by the installer) so a crash re-runs
the broker with a 5s backoff.

## OpenCode adapter choice

The broker observes state from the **shared global `opencode.db`** (TUI and
`opencode serve` both write it), so it needs **no plugin installed into the
OpenCode runtime** and covers every session type. This is the research's
"known reachable" integration, verified against the live DB on this machine and
against SQLite fixtures in `tests/test_observe.py`. A TUI plugin (research
section 5) is the preferred alternative if the installed runtime is verified to
support it; the broker/registry/focus/device layers are unchanged either way.

**Process-exit observation** (research sections 6, 7): on each tick the adapter
checks each launch's process (PID + verified creation time, via `psutil` with a
stdlib/ctypes fallback in `opendeck_broker/process.py`). When the OpenCode
process dies, its slot clears to black immediately -- a saved conversation does
not keep a dead TUI's button lit. A reused PID is guarded by the creation-time
pair. See `tests/test_process.py`.

## Environment

`OPENDECK_BROKER_HOST` (127.0.0.1), `OPENDECK_BROKER_PORT` (8899),
`OPENDECK_KEY_SIZE` (144), `OPENCODE_DB` (path to opencode.db),
`OPENDECK_MINI_SERIAL`, `OPENDECK_HEARTBEAT_S` (2), `OPENDECK_LEASE_S` (10),
`OPENDECK_BROKER_HOME` (token store location).

## Verified vs. needs the physical Mini

Verified headless (this branch, `python -m pytest tests`): the reducer
(precedence INPUT > RUN > IDLE, idle does not clear pending requests), the
six-slot registry (no compaction, overflow, generations, stale/epoch rejection),
the DB observer (against a real SQLite fixture), the focus resolve/verify
logic (against injected window/foreground fakes), the broker render/press path
(mock device), and the REST API round-trip.

Needs the physical Mini + a foregrounded second app (run with the hardware):
`tools/probe_device.py` (ownership, 6 black, 6 numbered, 6 key events) and
`tools/probe_focus.py` (real press -> verified foreground). These are the
acceptance rows the research says must not be claimed from a simulated API pass.
