$ErrorActionPreference = 'Stop'
$data = Join-Path $env:USERPROFILE '.opencode-deck'
$installPath = Join-Path $data 'install.json'
if (-not (Test-Path $installPath)) { throw 'No installation metadata found.' }
$install = Get-Content $installPath -Raw | ConvertFrom-Json
try { & $install.python -m ocdeck stop } catch {}
$task = Get-ScheduledTask -TaskName 'OpenCode Deck' -TaskPath '\' -ErrorAction SilentlyContinue
if ($task -and $task.Description -like 'OpenCode Deck*') {
    Stop-ScheduledTask -TaskName 'OpenCode Deck' -TaskPath '\'
    Unregister-ScheduledTask -TaskName 'OpenCode Deck' -TaskPath '\' -Confirm:$false
}
$entry = Join-Path $install.configDir 'plugins\ocdeck.js'
if ((Test-Path $entry) -and (Get-Content $entry -Raw).StartsWith('// Managed by OpenCode Deck installer')) {
    Remove-Item -LiteralPath $entry
}
$bin = Join-Path $data 'bin'
$entries = @([Environment]::GetEnvironmentVariable('Path','User') -split ';' | Where-Object { $_ -and $_ -ne $bin })
[Environment]::SetEnvironmentVariable('Path', ($entries -join ';'), 'User')
Write-Host 'Task and server-plugin entry removed. Local logs/config/venv retained.'
Write-Host 'If you selected TUI mode, remove its file URI from tui.json. Re-enable Mini in Elgato if desired.'
