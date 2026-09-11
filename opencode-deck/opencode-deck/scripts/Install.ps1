param(
    [string]$Python = 'python',
    [string]$OpenCodePath,
    [string]$ConfigDirectory,
    [ValidateSet('server','tui')][string]$PluginMode = 'server'
)
$ErrorActionPreference = 'Stop'
$source = Split-Path -Parent $PSScriptRoot
$data = Join-Path $env:USERPROFILE '.opencode-deck'
$old = $null
if (Test-Path (Join-Path $data 'install.json')) {
    $old = Get-Content (Join-Path $data 'install.json') -Raw | ConvertFrom-Json
}
if (-not $OpenCodePath) {
    if ($old -and (Test-Path -LiteralPath $old.opencode)) { $OpenCodePath = $old.opencode }
    else {
        $command = Get-Command opencode -ErrorAction SilentlyContinue
        if ($command) { $OpenCodePath = $command.Source }
    }
}
if (-not $OpenCodePath -or -not (Test-Path -LiteralPath $OpenCodePath)) {
    throw 'Install OpenCode first, or pass -OpenCodePath with its actual executable/shim path.'
}
if ($OpenCodePath.StartsWith((Join-Path $data 'bin'), [StringComparison]::OrdinalIgnoreCase)) {
    throw 'OpenCodePath points to this launcher. Supply the original OpenCode executable.'
}
& $Python -c 'import sys; assert sys.version_info >= (3,11), "Python 3.11 or newer required"'
if ($LASTEXITCODE -ne 0) { throw 'Python 3.11+ is required; use -Python with its executable path.' }
New-Item -ItemType Directory -Force -Path $data | Out-Null
# Per-user token/discovery protection. Do not broaden ACLs or require an administrator.
$user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
& icacls.exe $data /inheritance:r /grant:r "${user}:(OI)(CI)F" 'SYSTEM:(OI)(CI)F' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Could not secure the per-user configuration directory.' }
$existingTask = Get-ScheduledTask -TaskName 'OpenCode Deck' -TaskPath '\' -ErrorAction SilentlyContinue
if ($existingTask -and $existingTask.Description -notlike 'OpenCode Deck*') {
    throw 'An unrelated task already uses the name OpenCode Deck; refusing to replace it.'
}
if ($existingTask) { Stop-ScheduledTask -TaskName 'OpenCode Deck' -TaskPath '\' }
$venv = Join-Path $data 'venv'
& $Python -m venv $venv
if ($LASTEXITCODE -ne 0) { throw 'Virtual environment creation failed.' }
$runtime = Join-Path $venv 'Scripts\python.exe'
& $runtime -m pip install --disable-pip-version-check -e $source
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed. Check Internet access and Python architecture.' }
$install = @{ python=$runtime; source=$source; opencode=$OpenCodePath; pluginMode=$PluginMode }
$install | ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $data 'install.json')
if (-not (Test-Path (Join-Path $data 'config.json'))) {
    @{fps=10;brightness=45;animations=$true;ready=$true;serial=$null} | ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $data 'config.json')
}
$pluginArgs = @('-m','ocdeck','install-plugin','--mode',$PluginMode)
if ($ConfigDirectory) { $pluginArgs += @('--config-dir',$ConfigDirectory) }
& $runtime @pluginArgs
if ($LASTEXITCODE -ne 0) { throw 'Plugin configuration failed. Read the message above; existing config was preserved.' }
$bin = Join-Path $data 'bin'
New-Item -ItemType Directory -Force -Path $bin | Out-Null
$cli = '@echo off' + "`r`n" + '"' + $runtime + '" -m ocdeck %*' + "`r`n"
$launch = '@echo off' + "`r`n" + '"' + $runtime + '" -m ocdeck launch -- %*' + "`r`n"
$route = '@echo off' + "`r`n" + '"' + $runtime + '" -m ocdeck route -- %*' + "`r`n"
Set-Content -LiteralPath (Join-Path $bin 'ocdeck.cmd') -Value $cli -Encoding ASCII
Set-Content -LiteralPath (Join-Path $bin 'oc.cmd') -Value $launch -Encoding ASCII
Set-Content -LiteralPath (Join-Path $bin 'opencode.cmd') -Value $route -Encoding ASCII
$userPath = [Environment]::GetEnvironmentVariable('Path','User')
$entries = @($userPath -split ';' | Where-Object { $_ -and $_ -ne $bin })
[Environment]::SetEnvironmentVariable('Path', (($bin + ';' + ($entries -join ';')).TrimEnd(';')), 'User')
$env:Path = $bin + ';' + $env:Path
$pythonw = Join-Path $venv 'Scripts\pythonw.exe'
$action = New-ScheduledTaskAction -Execute $pythonw -Argument '-m ocdeck broker' -WorkingDirectory $data
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $user
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName 'OpenCode Deck' -TaskPath '\' -Description 'OpenCode Deck animated Mini broker (per-user interactive logon)' -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
Start-ScheduledTask -TaskName 'OpenCode Deck' -TaskPath '\'
Write-Host ''
Write-Host 'Installed. Disable this Mini in Elgato Preferences > Devices.'
Write-Host 'Open a NEW terminal, run: opencode     (or: oc / ocdeck launch)'
Write-Host 'Verify Get-Command opencode resolves to .opencode-deck\bin\opencode.cmd.'
Write-Host 'Global plugin also loads for normal opencode launches; managed windows give reliable identity.'
Write-Host 'Run: ocdeck status     and read docs\FIRST-RUN.md for physical acceptance tests.'
Write-Host "Keep this bundle directory at: $source"
