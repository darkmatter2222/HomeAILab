# opendeck-broker — requirement traceability (handoff)

Maps the key requirements in `docs/streamdeck-opencode-research.md` to where they
are implemented, the test that proves them, and their status. "Headless-verified"
means proven by `python -m pytest tests` (87 tests) without the physical Mini.
"Physical-pending" means it needs the real Mini (and, for focus, a second
foreground app); the probe tool is ready but the row is not yet claimed as passed
per research section 14 ("Do not report the reboot, USB, or physical-press tests
as passed from a simulated API test").

## The four critical rules (research preamble)

| Rule | Where | Evidence | Status |
|---|---|---|---|
| One device owner | `device/base.py` + `main.py` (option A: broker owns the Mini over HID; Elgato has the device disabled) | `test_e2e_mock`, `test_integration` | headless-verified (physical ownership = `probe_device.py`) |
| One button per live TUI instance | `registry.register` (per-instance slot) | `test_registry`, `test_protocol` | headless-verified |
| State derived from actual runtime facts | `opencode/observe.py` (global DB) + `opencode/process.py` (process exit) | `test_observe`, `test_process`, live-DB check | headless-verified |
| Presses only focus windows (no state mutation) | `broker._handle_press` -> `focus.focus_marker` | `test_e2e_mock::test_register_render_press_focus_cycle`, B-14 | headless-verified |
| Press focuses without a new registration / epoch bump (research 11) | `broker.on_key` captures occupant+gen; `_handle_press` is read-only on registry | `test_e2e_mock::test_press_does_not_change_registration_or_epoch` | headless-verified |

## Behavior contract (research section 2)

| Requirement | Where | Evidence | Status |
|---|---|---|---|
| No TUI -> black, no text; press = nothing | `model.derive_display`, `broker._handle_press` | `test_reducer`, B-01, B-15 | headless-verified |
| Ready -> amber IDLE; press focuses | reducer + focus | B-02, `test_e2e_mock` | headless-verified |
| Busy/generating/tool/retry -> green RUN | reducer (`Status.BUSY`/`RETRY`) | B-05, B-06, B-07 | headless-verified |
| Unresolved permission/question -> red INPUT; press focuses, doesn't answer | reducer precedence | B-08, B-09, B-10 | headless-verified |
| Instance dies -> slot black | `opencode/adapter.refresh` (process exit) + `process.is_alive` | `test_process`, B-18, B-19 | headless-verified |
| Six slots row-major; no compaction; overflow (7th) not silent | `registry` (row-major, lowest-free, `overflow()`) | `test_registry`, B-03, B-23 | headless-verified |
| Verify physical indexing with six numbered images | `tools/probe_device.py` | numbered-image upload + key events | **physical-pending** |

## Identity / protocol (research section 7)

| Requirement | Where | Evidence | Status |
|---|---|---|---|
| Fresh UUID per launch; immutable identity | `opencode/adapter.register_launch` | `test_protocol` | headless-verified |
| Pair PID with creation time (reuse guard) | `process.is_alive`, `model.Process.matches` | `test_process::test_pid_reuse_guarded_by_start_time` | headless-verified |
| Monotonic sequence within a producer epoch; reject stale | `registry.accept_snapshot` | `test_registry::test_stale_sequence_rejected` | headless-verified |
| Slot reuse increments a generation; delayed press doesn't hit new occupant | `registry` (generation, `validate_press`) | `test_registry::test_stale_press_does_not_focus_new_occupant`, B-20 | headless-verified |
| Broker restart changes epoch; client re-registers with full snapshot | `registry.broker_epoch` | `test_registry::test_different_epoch_rejected_without_reregister`, B-21 | headless-verified |
| Heartbeat renews presence, returns broker epoch | `registry.heartbeat`, `api /heartbeat` | `test_registry::test_heartbeat_returns_broker_epoch` | headless-verified |
| Endpoints (register/snapshot/heartbeat/delete/display/deck/focus/diagnostics) | `api.py` | `test_api` (REST + SSE) | headless-verified |
| Press accepts a known instance id, not an arbitrary command | `broker._handle_press` (resolves occupant -> fixed marker) | `test_e2e_mock` | headless-verified |
| Switching conversation inside a TUI keeps the same slot + binding (research 14) | `adapter.refresh` (per-directory tracked TUI) | B-17 (models a real session-id change) | headless-verified |

## State reducer (research section 6)

| Requirement | Where | Evidence | Status |
|---|---|---|---|
| `idle` must not erase outstanding requests | `model.Instance.set_status` + reducer | `test_reducer::test_idle_does_not_erase_outstanding_requests` | headless-verified |
| INPUT > RUN > IDLE precedence | `model.derive_display` | `test_reducer` | headless-verified |
| Child completes while parent runs -> parent stays green | per-directory aggregation | B-11 | headless-verified |
| Child needs input -> owning TUI red, no extra slot | per-directory aggregation | B-12 | headless-verified |
| Ordinary-prose question is IDLE, not INPUT | reducer (only structured requests = INPUT) | B-13 | headless-verified |
| Recover pending requests from a snapshot after reconnect | `adapter.refresh` re-reads DB | B-21 | headless-verified |
| UNKNOWN for untrustworthy/disconnected telemetry (not a lying green) | `model` (`telemetry_trusted`) + adapter | B-24 | headless-verified |
| Observer reads the live DB read-only (never grabs OpenCode's write lock) | `observe.DbObserver` (file URI `mode=ro`) | `test_observe::test_observer_opens_db_read_only`, live-DB read | headless-verified |

## Device / startup / recovery (research sections 3, 8)

| Requirement | Where | Evidence | Status |
|---|---|---|---|
| Open Mini, explicitly upload six black (not assume `reset`) | `broker.start` -> `upload_black_frame` | `test_e2e_mock::test_start_uploads_six_black`, B-01 | headless-verified (physical = `probe_device.py`) |
| Render identity+state into one image (no stale title) | `images.render_key` | `test_images`, B rows | headless-verified |
| Cache identical images; don't re-upload unchanged keys over USB | `broker._upload` + `_rendered` cache | `test_e2e_mock::test_render_caches_identical_images` | headless-verified |
| Refresh tick meets the 500 ms state-update target (research 14) | `main.run` tick = `config.tick_seconds` (default 0.5 s) | `test_config::test_tick_default_meets_500ms_state_target` | headless-verified (measure real latency on host) |
| On USB reconnect, upload the complete frame | `broker.render` (full frame) | B-22 | headless-verified (physical replug pending) |
| Broker restart: fresh registry, re-register before colors | `main.run` (new Registry), B-21 | B-21 | headless-verified |
| Fallback cleanup within the configured lease window (research 14) | `registry.sweep_expired` + `broker.sweep` (per-tick, `lease_seconds`) | `test_registry::test_lease_sweep_frees_a_quiet_producer`, `test_lease_sweep_heartbeat_keeps_instance_alive` | headless-verified |
| Graceful shutdown black-outs keys | `broker.stop` -> `upload_black_frame` | `test_e2e_mock::test_stop_blacks_out_colored_keys` | headless-verified |
| Logon auto-start + restart-on-failure, interactive session | `tools/install-autostart.ps1` | parse-checked | **physical-pending** (run on host) |

## Focus (research section 10)

| Requirement | Where | Evidence | Status |
|---|---|---|---|
| Unique launch token = window identity (not title/PID) | `adapter.register_launch`, `focus.launch_project` | `test_focus` (launch marker), B-04 | headless-verified |
| Resolve marker -> exactly one window; else NOT_FOUND/AMBIGUOUS | `focus.WindowsFocusAdapter.resolve` | `test_focus` | headless-verified |
| Restore if minimized; verify actual foreground window | `focus.focus` (`ShowWindow` + `GetForegroundWindow`) | `test_focus::test_success_when_foreground_confirmed`, `test_focus_denied_when_foreground_not_our_window` | headless-verified (physical = `probe_focus.py`) |
| A stale button never falls through to creating a window | marker scan (no `wt -w NAME` create) | `test_focus::test_not_found` | headless-verified |
| Real press foregrounds the correct terminal while another app is active | `tools/probe_focus.py` | real press + foreground verify | **physical-pending** |

## Physical acceptance rows (research section 14) — pending the Mini

| ID | Row | Probe / evidence | Status |
|---|---|---|---|
| A-own | Ownership + 6 black + 6 numbered + 6 key events | `tools/probe_device.py` | physical-pending |
| A-focus | Real-press focus with a 2nd app foreground | `tools/probe_focus.py` | physical-pending |
| A-boot | Cold reboot, no OpenCode -> six black, no old sessions | reboot host, observe Mini | physical-pending |
| A-order | Broker before/after Elgato both work | start/stop ordering with Elgato app | physical-pending |
| A-replug | USB reconnect restores the full frame | re-plug the Mini | physical-pending |
| A-power | Lock/unlock/sleep/resume: no stale green | sleep/wake the host | physical-pending |
| A-min | Focus a minimized instance from another app | minimize target, press from another app | physical-pending |

## How to re-verify

```
cd opendeck-broker
python -m pytest tests -q     # 87 pass
python tools/acceptance.py    # 24/24 headless; writes acceptance-report.md
python tools/selftest.py      # simulated end-to-end demo
```

Then, with the Mini attached (disabled in Elgato > Preferences > Devices > Enabled):
`python tools/probe_device.py` and `python tools/probe_focus.py`, plus the A-* rows.
