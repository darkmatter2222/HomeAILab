$ErrorActionPreference = 'Stop'
$data = Join-Path $env:USERPROFILE '.opencode-deck'
$runtime = Join-Path $data 'venv\Scripts\python.exe'
Write-Host 'Command resolution:'
Get-Command opencode,oc,ocdeck -ErrorAction SilentlyContinue | Select-Object Name,Source
Write-Host 'Scheduled task at root:'
Get-ScheduledTask -TaskName 'OpenCode Deck' -TaskPath '\' | Select-Object TaskName,TaskPath,State
Get-ScheduledTaskInfo -TaskName 'OpenCode Deck' -TaskPath '\' | Select-Object LastRunTime,LastTaskResult
Write-Host 'Native device inventory:'
& $runtime -m ocdeck devices
Write-Host 'Broker status (mock must be false on your PC):'
& $runtime -m ocdeck status
Write-Host 'These checks do not prove physical imagery or keyboard focus. Follow FIRST-RUN.md.'
