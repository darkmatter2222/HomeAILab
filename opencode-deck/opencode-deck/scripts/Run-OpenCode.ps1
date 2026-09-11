param([Parameter(Mandatory=$true)][string]$LaunchFile)
$ErrorActionPreference = 'Stop'
$spec = Get-Content -LiteralPath $LaunchFile -Raw | ConvertFrom-Json
Set-Location -LiteralPath $spec.cwd
$arguments = @($spec.args)
& $spec.executable @arguments
exit $LASTEXITCODE
