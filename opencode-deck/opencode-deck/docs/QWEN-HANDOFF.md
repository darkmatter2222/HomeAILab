# Deployment goal prompt for Qwen 3.8 27B

You are working locally on the owner's Windows PC. Install and finish validating this source bundle, preserving existing Home AI / HomeAILab work and OpenCode configuration. The owner authorizes this integration and will disable the Mini in Elgato Preferences > Devices. Do not assume that this bundle has been verified with their physical hardware or their installed OpenCode version.

## Required outcome

One per-user broker owns a six-key Stream Deck Mini directly through USB HID. With no live OpenCode instances, key 1 shows animated cyan READY and the others are black. Each independent interactive OpenCode instance occupies one stable key: green animated running/retry, amber idle, red pulsing pending permission or structured question. Pending input takes precedence over running. Pressing a key focuses exactly its terminal window without answering permissions, typing, changing session state, or cycling sessions. Closing the runtime removes its key; other instances do not shift. All six slots are available to instances. A seventh waits for a vacancy. Stale telemetry is explicitly unknown, not confidently idle.

The service starts through the root Task Scheduler task `\OpenCode Deck` at this user's logon, in the interactive session. Use logon rather than a SYSTEM pre-login service because focusing desktop windows requires the user's session. Bind loopback with port 0 and use the atomic discovery file; never hard-code a common port. Keep Elgato disabled for this physical device so profiles cannot repaint it. Do not install an Elgato plugin or use MCP for this direct-HID design.

## Read before changing code

Read README.md, FIRST-RUN.md, ARCHITECTURE.md, API.md, TEST-RESULTS.md and REMOTE-AND-WSL.md. Inspect the existing Home AI repo, its applicable AGENTS.md, `git status`, uncommitted diffs, and any previous deck implementation. Do not discard or commit unrelated work. This bundle is standalone because the remote author's environment did not contain the user's uncommitted implementation. Reconcile actual local requirements before moving files into the repo.

Record Windows version, terminal version, Python executable/version/architecture, original OpenCode command and version, config home (including overrides), plugin API support, Mini model/serial, Elgato version and device-disabled setting. Do not print provider keys or broker token. The installer records the original OpenCode executable; never point it to its own wrapper.

## Implementation inventory

- `ocdeck/model.py`: process identity and leases, six stable slots, overflow, sequence/producer epoch handling, pending precedence, generation-safe focus.
- `ocdeck/broker.py`: singleton, authenticated local HTTP, discovery, process sweep, device/focus orchestration and logs.
- `ocdeck/device.py`: pinned StreamDeck Mini protocol driver with wheel-provided HID transport, native frame cache, reconnect and physical key capture.
- `ocdeck/art.py`: generated animation frames; no downloaded imagery needed.
- `ocdeck/focus.py`: exact dedicated-window title token, pointer-sized Win32 calls, foreground verification, paired thread attachment fallback.
- `ocdeck/launcher.py`: one Windows Terminal window per instance, exact lifetime, binding environment and global plugin installation.
- `plugins/core.mjs`: snapshot transport, instance registration, heartbeat/reconnect, runtime claim and state facts.
- `plugins/server.mjs`: conventional global OpenCode plugin; this is the installer default.
- `plugins/tui.mjs`: optional newer TUI plugin API; do not enable without confirming installed API compatibility.
- `scripts/Install.ps1`: editable Python environment, global wrapper/plugin, per-user secured state, root scheduled task.

## Execute in order

1. Place the entire source folder permanently, e.g. `C:\Tools\opencode-deck`. Install Python 3.11+ and Windows Terminal if absent. Resolve the original OpenCode executable before changing PATH.
2. Verify that Elgato has the Mini disabled. Stop earlier competing hardware controllers. Run `scripts/Install.ps1` as the desktop user, supplying `-OpenCodePath` and `-ConfigDirectory` if needed. If root Task Scheduler registration is denied, elevate as the same user for registration; never install it as another account or SYSTEM. Read failures; do not silently skip setup steps.
3. In a fresh terminal, verify `Get-Command opencode`, `ocdeck status`, and `scripts/Verify-Windows.ps1`. Machine PATH or aliases can outrank the wrapper; resolve that or use the explicit `oc` / `ocdeck launch` launcher. Preserve noninteractive CLI passthrough behavior.
4. Stop the broker and run `ocdeck hardware-check`. Visually confirm six numbered images, then press physical keys 1 through 6. Read the saved diagnostic. Restart the task. Check READY physically; `online: true` alone cannot prove pixels are visible.
5. Run `scripts/Test.ps1`. Install Node 20+ if running the JavaScript tests. If practical, set `OPENCODE_TEST_BIN` to the original OpenCode executable and run `tests/live_opencode.py`; its local fake model avoids requiring a real provider. This optional fixture may need adaptation for Windows subprocess launch semantics or the installed OpenCode API. It was not validated against a live runtime in the authoring environment.
6. Launch one managed OpenCode from each of two unrelated project directories. Ensure exactly one registration per live terminal. Exercise an actual model turn, actual permission prompt, and actual structured question. Verify green -> red -> green/amber transitions, including rejection/cancellation, multiple pending requests, and background subagent activity. Test opening an existing session and changing sessions. Compare runtime event payloads with adapter expectations before patching.
7. Test each physical key from another app, with the target minimized, and with multiple Windows Terminal windows open. Verify the exact target becomes foreground. Never accept a mocked API return or a synthetic HTTP focus request as proof of a working physical button. If Windows foreground policy blocks activation, capture `lastFocus` and inspect Win32 return/last-error values. Do not send keystrokes or focus a guessed window to disguise the failure.
8. Launch six; confirm fixed slots. Launch seven; confirm overflow behavior. Close a middle instance; confirm vacancy goes to the oldest overflow instance and other live assignments remain. Test graceful exit and forced process termination. A dead PID or reused PID must never focus an unrelated window.
9. Restart the broker while instances remain open. Confirm rediscovery and full state restoration, including a pending prompt. Kill the broker and verify task recovery. Unplug/replug USB and verify full repaint. Restart Elgato while the device remains disabled. Reboot, sign in, and confirm READY without manual startup. Launch again and recheck focus.
10. Update TEST-RESULTS.md with exact local versions and observed outcomes. Fix concrete failures in place; editable installation picks up Python changes, while plugin or process changes require restart. Rerun tests relevant to each fix. Deliver a short user report with commands used, evidence, and any genuinely remaining limitations.

## Known areas to investigate locally

The conventional OpenCode plugin may expose session/permission/question snapshot methods differently by version. Events drive live state, but complete reconciliation after hot reload requires authoritative snapshots. If required methods are absent, add a version-correct official SDK/HTTP adapter and a regression fixture; do not invent methods or mark unavailable snapshots as successfully reconciled. Confirm actual event names and payloads against installed upstream source.

The default adapter assumes one independent local OpenCode runtime per managed terminal. A server shared by multiple `attach` clients cannot be separated correctly merely by process-wide session events. The newer TUI adapter is the intended route-specific integration when supported, but needs local validation. Do not treat global plugin installation as automatic WSL/SSH/container support. If that is needed, implement the host relay described in REMOTE-AND-WSL.md and extend tests.

Win32 focus is best effort under Windows foreground restrictions, especially across elevated/non-elevated apps. Exact managed-window mapping and explicit failure reporting already exist; verify them on this PC. Do not remove identity validation, bearer authentication, Origin rejection, sequence ordering, producer epochs, or slot generations to make a test pass.

## Completion criteria

Software tests pass; the real OpenCode plugin emits all three requested states; physical keys focus the exact six windows; closed processes disappear; pending state survives broker restart; USB reconnect and reboot/logon recover; empty slots are black; READY yields its slot; existing OpenCode configuration remains intact. Until these observations are recorded, describe the integration as implemented but still undergoing local validation.
