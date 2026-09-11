# Verification record

Bundle final verification: 2026-09-08. Environment: Linux authoring workspace, Python 3.12, Node, Pillow, psutil 7.2.2, streamdeck 0.10.0 and hidapi 0.15.0. No physical Stream Deck or Windows desktop was available.

## Passed here

- **23 Python unittest tests passed**, including a real JavaScript-to-Python HTTP integration scenario. Exact final output: `python-test-output.txt`.
- **5 JavaScript state tests passed**. Exact output: `javascript-test-output.txt`.
- Python implementation source parses, and each plugin passes `node --check`.
- Animated preview was generated and visually inspected. This is rendered artwork, not a photograph or proof of hardware operation.

The Python suite covers six stable assignments and overflow, concurrent registrations, pending-input priority, busy/retry mapping, closing and actual process death, PID reuse rejection, stale state, out-of-order snapshots and retired producer epochs, generation-safe button handling, singleton lock, blank-key no-op, READY relinquishing a slot, authenticated real HTTP registration/update/deletion, and Origin rejection.

One Python test launches Node and drives the real Bridge class through the real Python broker HTTP server. It verifies pending state recovery after losing a registry entry. It also loads the actual conventional plugin entrypoint with a fixture SDK client and sends permission/question/status hooks through the broker. The final extension verifies that an explicit SDK snapshot failure produces unknown and later recovers to running. This exercises the plugin code but **is not equivalent to OpenCode loading it**.

The image protocol test uses the actual pinned StreamDeck Mini driver and Pillow native conversion, checking encoded image packets with a fake transport. Callback tests exercise key-down behavior and captured assignment generation. They do not test the operating system's physical HID driver or USB timing.

This workspace exposes a process namespace mismatch between runtime PIDs and `/proc`. The suite contains a test-only identity translator for that environment. Production Windows PID validation is unchanged. Test dependencies were installed outside the bundle for authoring; the Windows installer installs its own environment.

## Unverified gates

| Gate | Status |
|---|---|
| Mini image appearance, orientation, all six physical callbacks | Requires user's device |
| USB reconnect / exclusive ownership after Elgato restart | Requires user's device and Windows |
| PowerShell installer and Task Scheduler registration/recovery | Requires Windows; scripts not executed here |
| Exact foreground activation/minimized-window restoration | Requires user's Windows desktop |
| Reboot -> user logon -> READY | Requires user's PC |
| Installed OpenCode loads plugin and emits real runtime events | Requires local validation |
| Optional newer TUI adapter | Source-based implementation; runtime compatibility unverified |
| WSL/SSH/container relay | Not implemented; see REMOTE-AND-WSL.md |

An OpenCode 1.18.29 package was downloaded and its `--version` checked. A live-runtime test was attempted using a local deterministic model fixture. Execution was interrupted by this environment's network approval controls (`network approval was cancelled before a decision was returned`); there was no successful end-to-end runtime result. The optional fixture remains in `tests/live_opencode.py` for local adaptation and verification. No claim of live OpenCode compatibility follows from the version check.

## Run locally

After installation, run `scripts/Test.ps1` (Node 20+ needed for JavaScript). Follow FIRST-RUN.md for real hardware, state, focus and reboot acceptance. `ocdeck hardware-check` requires the broker stopped and records actual key-down events. Its display-confirmation field remains false because a program cannot verify visible pixels merely by submitting images.

Record local outcomes here, including OpenCode and terminal versions, adapter mode, serial/model, exact failed step, relevant redacted logs, and eventual fix. Do not replace an unverified gate with “passed” based on code inspection or a simulated test.
