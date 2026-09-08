# install-autostart.ps1 -- register the broker to start at user logon.
#
# Research sections 4 + 8: run at user logon with restart-on-failure, in the
# INTERACTIVE user session (a Session-0 service cannot operate the logged-in
# user's windows). Task Scheduler "run only when user is logged on" gives us the
# interactive session. Restart-on-failure is provided by a small supervisor loop
# wrapper so a crash re-runs the broker with a backoff.
#
# Idempotent: safe to re-run. Run from an elevated or normal PowerShell:
#   powershell -ExecutionPolicy Bypass -File tools\install-autostart.ps1
# Uninstall:
#   powershell -ExecutionPolicy Bypass -File tools\install-autostart.ps1 -Remove

param([switch]$Remove)

$ErrorActionPreference = "Stop"
$TaskName = "OpenDeckBroker"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$Python   = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $Python) { throw "python not found on PATH" }

# A supervisor wrapper: restart-on-failure with a 5s backoff.
$Supervisor = @"
@echo off
REM opendeck-broker supervisor: restart on failure, 5s backoff.
setlocal
REM run from the opendeck-broker package dir (this .bat lives in tools\).
cd /d "%~dp0.."
:loop
"$Python" -m opendeck_broker.main
echo opendeck-broker exited with %errorlevel% at %date% %time%
timeout /t 5 /nobreak >nul
goto loop
"@
$SupPath = Join-Path $RepoRoot "tools\opendeck-broker-supervisor.bat"
Set-Content -Path $SupPath -Value $Supervisor -Encoding ASCII
Write-Host "wrote supervisor: $SupPath"

if ($Remove) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "removed scheduled task $TaskName"
    exit 0
}

$action  = New-ScheduledTaskAction -Execute $SupPath
# principal: current user, interactive session, whether logged on or not is
# deliberately NOT set (we want "run only when logged on" = interactive).
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)

Register-ScheduledTask -TaskName $TaskName -Action $action -Principal $principal `
    -Trigger $trigger -Settings $settings -Force | Out-Null
Write-Host "registered scheduled task '$TaskName' (logon, interactive user, restart-on-failure)."
Write-Host "Start now:  Start-ScheduledTask -TaskName $TaskName"
Write-Host "Stop now:   Stop-ScheduledTask  -TaskName $TaskName"
