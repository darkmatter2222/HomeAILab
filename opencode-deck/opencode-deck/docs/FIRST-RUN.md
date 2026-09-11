# Install and verify on Ryan's PC

1. Extract the ZIP to a permanent directory, for example `C:\Users\ryans\source\repos\opencode-deck`. Keep the whole folder: the installed Python package is editable and the global plugin entry imports these sources.
2. Disable only the Mini under Elgato Preferences > Devices > Enabled. Elgato 7.1 introduced that control, so 7.2 should have it. Close any old scripts that also write to the Mini. Leave Elgato running if you want; it must not own this device.
3. Confirm Python and OpenCode run. Use `Get-Command opencode` to record the original path before installing. Use Python 3.11 or later; the installer's `-Python` option accepts a full executable path.
4. Run the installer as the Windows account that will use the device. The default server plugin is the broad-compatibility path. Do not opt into TUI mode until the installed OpenCode API has been checked.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\Install.ps1
```

Alternative with explicit paths:

```powershell
.\scripts\Install.ps1 -Python 'C:\Path\To\python.exe' -OpenCodePath 'C:\Path\To\opencode.exe'
```

If the default OpenCode config home is overridden, use `-ConfigDirectory 'C:\actual\config\opencode'`. The installer otherwise honors `OPENCODE_CONFIG_DIR`, then `XDG_CONFIG_HOME`, then `~/.config/opencode`. Avoid installing another copy of the bridge in `.opencode/plugins` within projects.

If Task Scheduler returns access denied, rerun PowerShell elevated as the **same Windows account**. Do not install as SYSTEM or another administrator's account. The installed task deliberately uses Interactive / Limited rather than a different security principal. The script stops with an error if it cannot create the task; it does not silently substitute a startup folder.

5. Open a new terminal. Verify `Get-Command opencode` points to `.opencode-deck\bin\opencode.cmd`. Existing PowerShell functions/aliases and machine PATH entries can take precedence. `oc` or `ocdeck launch` explicitly selects the managed launcher if needed. Do not change the recorded original executable to this new shim.
6. Run `ocdeck status`. Expect `device.online: true` and `device.mock: false`. Verify the physical READY key. READY means the device was opened and images submitted, not that a camera has confirmed the screen or all focus tests have passed.
7. Run `opencode` from two different directories. Expect two separate terminal windows and two amber indicators. Run a real prompt and watch green during the entire work, then amber. Request a structured question and a tool approval to check red. The broker does not approve anything when a key is pressed.
8. With a different application foregrounded, press each physical key. Verify both the correct window and where keyboard input goes. Minimize a window and repeat. `ocdeck focus 1` tests a synthetic focus request; it does not replace a physical button test. `lastFocus` in status records the outcome.
9. Close one OpenCode instance. Its key should go black within approximately one second. Close the last instance: READY returns. Launch six; all six positions must work. A seventh remains off-deck until a slot frees.
10. Restart the broker, restart Elgato, unplug/replug USB, and reboot. Repeat mixed running/idle/input states. Check the task at the root of Task Scheduler after login.

**Standalone physical-key diagnostic**

```powershell
ocdeck stop
ocdeck hardware-check
Start-ScheduledTask -TaskName 'OpenCode Deck' -TaskPath '\'
```

The diagnostic takes the same process lock, draws six numbers, and asks you to press 1 through 6. It saves actual key-down results in `.opencode-deck\hardware-check.json`. It leaves visual confirmation explicitly false until you separately confirm appearance. Stop the broker first; two USB owners are not allowed.

**Configuration:** edit `.opencode-deck\config.json` and restart the task. Defaults: `fps: 10`, `brightness: 45`, `animations: true`, `ready: true`, `serial: null`. Use the serial from `ocdeck devices` when multiple Minis are present. `fps` is capped at 15. Set `animations` false for static status images, or lower FPS for USB load. Set `ready` false for six black keys when empty.

**Troubleshooting:** inspect `.opencode-deck\broker.log` and OpenCode's own logs. LINK ? indicates missing/failing/stale telemetry. A red key requires unresolved request data; the monitor does not interpret ordinary prose questions. A window-mapping error means the direct launch was not a dedicated managed window, its title changed, or a different terminal hosted it. A foreground-denied error is distinct from an absent target. A task with a long-running status is expected while the broker is active.

Before login or device initialization, firmware may display a logo or old image briefly. The application guarantees its initialized state, not a pre-firmware black screen.
