$ErrorActionPreference = 'Stop'
$source = Split-Path -Parent $PSScriptRoot
$runtime = Join-Path $env:USERPROFILE '.opencode-deck\venv\Scripts\python.exe'
if (-not (Test-Path $runtime)) { $runtime = 'python' }
Push-Location $source
try {
    & $runtime -m unittest discover -s tests -v
    if ($LASTEXITCODE -ne 0) { throw 'Python/integration tests failed' }
    & node --test tests/facts.test.mjs
    if ($LASTEXITCODE -ne 0) { throw 'JavaScript tests failed' }
} finally { Pop-Location }
