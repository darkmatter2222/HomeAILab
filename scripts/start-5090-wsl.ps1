# ============================================================================
# start-5090-wsl.ps1 - robust 5090 vLLM starter (for WSL2DockerAutostart)
#
# Keeps WSL alive with a PERSISTENT powershell.exe process that owns wsl.exe
# for the full health-wait (up to $TimeoutSec). The VM cannot be torn down
# while wsl.exe is connected, so the vLLM model load survives.
#
# Log : C:\Users\ryans\5090-wsl-start.log
# Exit: 0 = healthy, 1 = distro missing, 2 = timeout, 3 = VM died mid-load
# ============================================================================
param(
    [string]$Distro   = 'Ubuntu',
    [int]   $TimeoutSec = 900,
    [int]   $PollSec    = 15,
    [string]$Log = 'C:\Users\ryans\5090-wsl-start.log'
)

function Write-Log([string]$msg) {
    $line = "[{0}] {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $msg
    # Append via .NET (tolerates concurrent readers like tail -F).
    for ($i = 0; $i -lt 3; $i++) {
        try {
            [System.IO.File]::AppendAllText($Log, ($line + [Environment]::NewLine), [System.Text.Encoding]::UTF8)
            break
        } catch { Start-Sleep -Milliseconds 200 }
    }
}

Write-Log "=== start-5090-wsl ==="

# --- 1. Is the distro installed? --------------------------------------------
$distros = (wsl.exe -l -q 2>&1) -split "\r?\n" | ForEach-Object { $_.Trim() } | Where-Object { $_ }
if ($distros -notcontains $Distro) {
    Write-Log "ERROR: distro '$Distro' not in wsl -l -q (got: $($distros -join ','))"
    exit 1
}

# --- 2. Start a PERSISTENT wsl holder ---------------------------------------
# Owns wsl.exe for the whole wait so the VM stays up while vLLM loads.
# -WindowStyle Hidden keeps wsl.exe attached to a console (a fully detached
# windowless wsl.exe exits after ~2s and takes the VM with it).
# -Wait (not --exec): the holder powershell BLOCKS on wsl.exe for as long as
# sleep infinity lives, so the VM cannot be torn down while the holder runs.
# Start-Process gives the holder its OWN process group (no console sharing
# with the task's tree), so the task's process-tree teardown does not drag
# the holder - and thus the VM - down with it.
#
# -WindowStyle Hidden (NOT -PassThru): the holder's powershell blocks on
# wsl.exe for as long as 'sleep infinity' lives. -PassThru would make the
# powershell.exe EXE itself the session leader of the wsl.exe session, so
# when the task tears down its process tree, wsl.exe's console leader dies,
# the session ends, and the VM shuts down. -WindowStyle Hidden launches the
# holder through conhost.exe instead, which becomes the console leader and
# keeps the wsl.exe session alive independently of the task's process tree.
$holderScript = "wsl.exe -d $Distro -- bash -c 'exec sleep infinity'"
$holder = Start-Process powershell.exe `
    -ArgumentList @('-NoProfile', '-NonInteractive', '-WindowStyle', 'Hidden', '-Command', $holderScript) `
    -PassThru
Write-Log "wsl holder started (pid $($holder.Id)) - VM now kept alive"

# --- 2b. Wait for the VM to actually come up --------------------------------
# Use /proc/uptime (a real command that returns a value) so the wsl.exe
# session stays alive long enough for the VM to finish booting.
$bootWait = 0
$vmUp = $false
while ($bootWait -lt 240) {
    Start-Sleep -Seconds 10
    $bootWait += 10
    try {
        $up = wsl.exe -d $Distro -- cat /proc/uptime 2>&1
        if ($up -match '^\d') { $vmUp = $true; break }
    } catch {}
    if ($holder.HasExited) {
        Write-Log "ERROR: holder pid $($holder.Id) exited after ${bootWait}s - VM never came up"
        exit 3
    }
}
if (-not $vmUp) {
    Write-Log "ERROR: VM not up after 240s"
    exit 3
}
Write-Log "VM up after ${bootWait}s (uptime: $($up.Trim()))"

# --- 3. Wait for vLLM health ------------------------------------------------
$elapsed = 0
$lastProgress = ''
try {
    while ($elapsed -lt $TimeoutSec) {
        try {
            $r = Invoke-WebRequest -Uri 'http://127.0.0.1:8006/health' -TimeoutSec 5 -UseBasicParsing -ErrorAction Stop
            if ($r.StatusCode -eq 200) {
                Write-Log "vLLM HEALTHY (200) after ${elapsed}s"
                exit 0
            }
            Write-Log "poll ${elapsed}s: health HTTP $($r.StatusCode)"
        } catch {
            if ($_.Exception.Response) {
                $code = [int]$_.Exception.Response.StatusCode
            } else {
                $code = 'conn-fail'
            }
            if ($code -ne $lastProgress) {
                Write-Log "poll ${elapsed}s: $code"
                $lastProgress = $code
            }
        }

        # Every minute, verify the VM is still alive.
        if ($elapsed -ge 60 -and ($elapsed % 60) -eq 0) {
            $now = wsl.exe -l -v 2>&1 | Out-String
            if ($now -match ([regex]::Escape($Distro) + '\s+Stopped')) {
                Write-Log "VM went Stopped at ${elapsed}s - model load was killed"
                exit 3
            }
        }

        Start-Sleep -Seconds $PollSec
        $elapsed += $PollSec
    }
    Write-Log "TIMEOUT after ${TimeoutSec}s - vLLM never became healthy"
    exit 2
}
finally {
    # --- 4. Keep the holder alive (do NOT release it) -----------------------
    # The holder powershell (-Wait on wsl.exe) outlives this script. When the
    # task process tree is torn down, services.exe (pid 750) adopts it as an
    # orphan - the task scheduler does NOT kill it. So the wsl.exe session and
    # the VM persist for the lifetime of the machine. It is cheap (one idle
    # bash 'sleep infinity'). The next task run (daily) finds the VM already
    # Running and reuses it. If the PC reboots, the holder is gone and a
    # fresh one is spawned on the next task run.
    Write-Log "wsl holder kept alive (pid $($holder.Id)) - VM persists until next reboot"
}
