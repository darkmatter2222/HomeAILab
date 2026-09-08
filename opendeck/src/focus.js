// focus.js — bring a session's terminal to the front.
//
// When we launch an opencode session we open a Windows Terminal tab with a
// stable window title marker (`[opencode:<alias>]`). Pressing a key for that
// project finds the terminal window whose title contains the marker and
// raises it. If no marker match is found we fall back to just activating
// Windows Terminal so the press never does nothing.

import { spawn, execFile } from "node:child_process";

const IS_WIN = process.platform === "win32";

// Launch opencode in a terminal in `path`, with a stable title so focus can
// find it later. `bat` is the launcher (e.g. opencode-3090-serve.bat).
export function launchProject(project, { onDone } = {}) {
  const marker = `opencode:${project.alias}`;
  const title = `[${marker}] opencode`;
  if (IS_WIN) {
    // Open a Windows Terminal tab in the project dir running the launcher bat.
    // `cmd /k` sets a stable console title (the wt tab title) that
    // focusSession matches on. The old PowerShell `-Command` string got
    // mangled when passed through `wt` (.NET tried to launch a file literally
    // named ` & C:\...\opencode-3090-serve.bat` -> 0x80070002); `cmd /k`
    // keeps the whole command as one quoted argument.
    const bat = project.bat || "opencode";
    const cmdLine = `title ${marker} opencode & ${bat}`;
    const child = spawn(
      "wt",
      ["-w", "new", "-d", project.path, "cmd", "/k", cmdLine],
      { stdio: "ignore", detached: true },
    );
    child.once("error", (e) => onDone && onDone(e));
    child.once("spawn", () => {
      child.unref();
      onDone && onDone(null);
    });
  } else {
    const child = spawn("open", ["-a", "Terminal", project.path], { stdio: "ignore", detached: true });
    child.once("spawn", () => { child.unref(); onDone && onDone(null); });
  }
}

// Focus the terminal window whose title contains `marker` (e.g. "opencode:homeai").
// Windows: EnumWindows + SetForegroundWindow. Falls back to activating
// Windows Terminal if no titled window is found.
export async function focusSession({ marker } = {}) {
  if (!marker) return;
  if (IS_WIN) {
    const target = String(marker).replace(/'/g, "''");
    const ps = `
$target = '${target}';
Add-Type -TypeDefinition 'using System; using System.Runtime.InteropServices; using System.Text; public class W { public delegate bool EP(IntPtr h, IntPtr l); [DllImport("user32.dll")] public static extern bool EnumWindows(EP cb, IntPtr l); [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr h, StringBuilder s, int n); [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h); [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h); [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int c); }';
$found = [IntPtr]::Zero;
[void][W]::EnumWindows({ param($h, $l) $sb = New-Object System.Text.StringBuilder 512; [void][W]::GetWindowText($h, $sb, 512); if ([W]::IsWindowVisible($h) -and $sb.ToString().ToLower().Contains($target)) { $script:found = $h; return $false }; return $true }, [IntPtr]::Zero);
if ($found -ne [IntPtr]::Zero) { [void][W]::ShowWindow($found, 9); [void][W]::SetForegroundWindow($found); exit 0 }
$wt = Get-Process -Name wt -ErrorAction SilentlyContinue | Select-Object -First 1;
if ($wt) { $wt.BringToFront(); exit 0 }
exit 1`;
    await new Promise((resolve) => {
      execFile("powershell.exe", ["-NoProfile", "-WindowStyle", "Hidden", "-Command", ps], (err) => resolve(err));
    });
  } else {
    // macOS: raise the terminal window by title via AppleScript.
    await new Promise((resolve) => {
      execFile("osascript", ["-e", `
with timeout of 7 seconds
tell application "Terminal"
  set matched to false
  repeat with w in windows
    if (name of w) contains "${marker}" then
      perform action "AXRaise" of w
      set frontmost to true
      set matched to true
      exit repeat
    end if
  end repeat
  if not matched then activate
end tell
end timeout`], (err) => resolve(err));
    });
  }
}

export default { launchProject, focusSession };
