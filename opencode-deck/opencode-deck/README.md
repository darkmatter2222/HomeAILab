# OpenCode Deck 1.0

An animated Stream Deck Mini controller for up to six OpenCode terminal instances.

**Start here:** extract this whole folder to a permanent location, read `docs/FIRST-RUN.md`, then run `scripts/Install.ps1` in PowerShell. Give your local Qwen agent `docs/QWEN-HANDOFF.md` to install, verify, and fix any machine-specific integration issues.

This bundle contains implemented source code, a per-user Windows installer, global OpenCode adapters, tests, a hardware diagnostic, documentation, and an animation preview. Core software tests passed here. **The physical Mini, Windows Task Scheduler, and Windows foreground activation were not tested on your PC. The real OpenCode runtime integration test remains unverified.** See `docs/TEST-RESULTS.md` for evidence and limits.

| Condition | Key appearance |
|---|---|
| Device online, no instances | Cyan animated READY on key 1; five black keys |
| Running or automatically retrying | Green moving ring |
| Idle | Amber breathing glow |
| Permission or structured question pending | Red pulsing attention icon |
| Telemetry unavailable/stale | Amber LINK ? |
| Empty slot | Black; press does nothing |

READY never reserves an agent slot. The first instance replaces it. All six positions can show agents. Closing an instance frees its slot without moving other live assignments. Overflow instances receive a free slot when one becomes available.

**Installation scope:** global for your Windows user and OpenCode config home, across project directories. The provided managed launcher opens one dedicated Windows Terminal window per instance for stable focus identity. This is not an automatic cross-machine deployment; WSL, containers, SSH, shared-server attachments, arbitrary tabs/panes, and other desktop operating systems need separate host/runtime integration. See `docs/REMOTE-AND-WSL.md`.

**Requirements:** Windows 10/11, Windows Terminal, Python 3.11+ (64-bit recommended), your existing OpenCode installation, and a Stream Deck Mini disabled in Elgato Preferences > Devices. Internet is needed for the initial pip dependency installation. Node 20+ is needed only for the JavaScript test suite; OpenCode runs the plugin itself. No GPU/model dependencies are added. No existing model/provider/permission configuration is replaced.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\Install.ps1
```

Open a fresh PowerShell window afterward:

```powershell
Get-Command opencode
opencode
ocdeck status
```

`opencode` should resolve to `%USERPROFILE%\.opencode-deck\bin\opencode.cmd`. The original OpenCode executable is recorded and remains available. `oc` and `ocdeck launch` are explicit alternatives if an existing alias or machine PATH takes precedence. Noninteractive commands such as `opencode run`, `serve`, and `--version` pass through.

Task Scheduler contains `\OpenCode Deck`, triggered at your user logon. It runs without a console window, uses a single-instance lock, and restarts after failure. Logon is intentional: USB control and foreground activation belong to your interactive Windows desktop. It does not run in the pre-login Session 0 desktop.

The server binds to `127.0.0.1:0`, allowing Windows to allocate a free port, and atomically writes `discovery.json`. There is no fixed port and no port scan. Clients reread discovery on requests, including after a restart.

**Files:** `ocdeck/` is the Python implementation; `plugins/` contains conventional server and opt-in TUI adapters; `scripts/` contains installation and diagnostics; `tests/` contains executable tests; `docs/` contains architecture, API, operation, research, verification, and the Qwen handoff.

Use `ocdeck stop` for a graceful shutdown. `scripts/Uninstall.ps1` removes the owned scheduled task and server-plugin entry and removes the launcher directory from the user PATH. It retains logs/configuration/venv. If using the optional TUI adapter, remove its URI from `tui.json` as instructed by the uninstaller.
