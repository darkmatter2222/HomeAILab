@echo off
REM No setlocal here: the `call`ed temp set-file must write into the CALLER's
REM environment scope, so this script's own temp vars are cleaned up by hand.

REM ============================================================================
REM load-env.bat - load KEY=VALUE pairs from .env into the caller's environment
REM
REM Called by every harness launcher right after `setlocal`. It looks for a
REM .env in this directory (harness\.env) first, then in the repo root
REM (HomeAILab\.env). The root .env is the single source of truth for lab
REM host IPs and the router API key - see .env.example at the repo root for
REM the full variable list, and harness\.env.example for the subset the
REM launchers use.
REM
REM Lines starting with # are skipped. Inline ` # comment` tails on a value
REM are stripped. Values must not contain double quotes.
REM ============================================================================

set "HARNESS_ENV_FILE="
if exist "%~dp0.env" (
    set "HARNESS_ENV_FILE=%~dp0.env"
) else if exist "%~dp0..\.env" (
    set "HARNESS_ENV_FILE=%~dp0..\.env"
)

if not defined HARNESS_ENV_FILE (
    echo [load-env] WARNING: no .env found in harness\ or the repo root.
    echo [load-env]            Copy harness\.env.example to harness\.env or the repo root .env.
    exit /b 0
)

REM .bat extension is required: `call` does not run a bare .tmp file as a
REM batch script.
set "HARNESS_SET_FILE=%TEMP%\harness-env-%RANDOM%-%RANDOM%.bat"

REM Parse the .env and emit `set "KEY=VALUE"` lines into a temp batch file,
REM then call it so the variables land in the CALLER's environment (env
REM changes in a child powershell process would not propagate back to cmd).
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command ^
  "$lines = @();" ^
  "Get-Content -LiteralPath $env:HARNESS_ENV_FILE | ForEach-Object {" ^
  "  $l = $_.Trim();" ^
  "  if ($l -and $l -notmatch '^^#') {" ^
  "    $i = $l.IndexOf('=');" ^
  "    if ($i -gt 0) {" ^
  "      $k = $l.Substring(0, $i).Trim();" ^
  "      $v = $l.Substring($i + 1).Trim();" ^
  "      $m = $v -match '^^(\S+)(\s+#.*)?$';" ^
  "      if ($m) { $v = $Matches[1]; }" ^
  "      $lines += ('set ' + [char]34 + $k + '=' + $v + [char]34);" ^
  "    }" ^
  "  };" ^
  "};" ^
  "[System.IO.File]::WriteAllText($env:HARNESS_SET_FILE, ($lines -join [Environment]::NewLine));"

call "%HARNESS_SET_FILE%"
del /q "%HARNESS_SET_FILE%" >nul 2>&1

set "HARNESS_ENV_FILE="
set "HARNESS_SET_FILE="
exit /b 0
