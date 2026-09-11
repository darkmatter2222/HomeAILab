@echo off
setlocal EnableExtensions
REM Load lab host IPs + router key from .env (harness\.env or the repo root .env).
call "%~dp0..\load-env.bat"

REM ============================================================================
REM Claude Code launcher for local Muse Glimmer via llama.cpp
REM
REM Behavior:
REM   1. Queries the OpenAI-compatible /v1/models endpoint.
REM   2. If exactly one model is available, selects it automatically.
REM   3. If multiple models are available, presents a numbered selection menu.
REM   4. Reads the selected model's context length from vLLM when available.
REM   5. Configures Claude Code to compact well before the hard context limit.
REM   6. Routes Claude Code and all ultracode subagents to the selected model.
REM   7. Starts local/offline Handy speech-to-text when available.
REM   8. Starts Claude Code in ultracode with permission checks bypassed.
REM
REM Recommended Handy push-to-talk shortcut:
REM   Ctrl+Alt+Space
REM
REM No model names are hard-coded in this launcher.
REM ============================================================================


REM ============================================================================
REM Local Muse Glimmer / llama.cpp configuration
REM ============================================================================

REM Claude Code appends /v1/messages to this origin.
set "ANTHROPIC_BASE_URL=http://127.0.0.1:8006"
set "ANTHROPIC_AUTH_TOKEN=local-vllm"

REM Used only if /v1/models does not expose a context-length field.
set "FALLBACK_CONTEXT_TOKENS=131072"

REM Context-safety policy.
REM
REM Claude Code normally waits until roughly 95%% capacity before compacting.
REM That is too close to the limit for a non-Anthropic model because Claude
REM Code's estimate and the Muse Glimmer tokenizer used by llama.cpp can differ.
REM
REM 85%% leaves a ~19.6K token safety margin on a 131,072-token slot.
set "DGX_AUTOCOMPACT_PERCENT=85"

REM Reserving 8192 output tokens leaves headroom for input and compaction.
set "DGX_MAX_OUTPUT_TOKENS=8192"

REM Temporary files used to return model metadata from PowerShell.
set "MODEL_FILE=%TEMP%\claude-dgx-model-%RANDOM%-%RANDOM%.tmp"
set "CONTEXT_FILE=%TEMP%\claude-dgx-context-%RANDOM%-%RANDOM%.tmp"


REM ============================================================================
REM Discover available models and their context limits
REM ============================================================================

echo.
echo Discovering models from:
echo   %ANTHROPIC_BASE_URL%/v1/models
echo.

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference = 'Stop';" ^
  "$headers = @{ Authorization = 'Bearer ' + $env:ANTHROPIC_AUTH_TOKEN };" ^
  "try {" ^
  "  $response = Invoke-RestMethod -Uri ($env:ANTHROPIC_BASE_URL.TrimEnd('/') + '/v1/models') -Method Get -Headers $headers -TimeoutSec 10;" ^
  "} catch {" ^
  "  Write-Host '';" ^
  "  Write-Host 'ERROR: Could not query the local llama.cpp Muse Glimmer endpoint.' -ForegroundColor Red;" ^
  "  Write-Host ('       ' + $_.Exception.Message);" ^
  "  exit 2;" ^
  "};" ^
  "$modelObjects = @(" ^
  "  $response.data |" ^
  "  Where-Object {" ^
  "    $null -ne $_.id -and ([string]$_.id).Trim()" ^
  "  }" ^
  ");" ^
  "$models = @(" ^
  "  $modelObjects |" ^
  "  ForEach-Object { ([string]$_.id).Trim() }" ^
  ");" ^
  "if ($models.Count -eq 0) {" ^
  "  Write-Host '';" ^
  "  Write-Host 'ERROR: The endpoint returned no usable model IDs.' -ForegroundColor Red;" ^
  "  exit 3;" ^
  "};" ^
  "if ($models.Count -eq 1) {" ^
  "  $selectedIndex = 0;" ^
  "  $selected = $models[0];" ^
  "  Write-Host ('Detected one model: ' + $selected);" ^
  "} else {" ^
  "  Write-Host ('Detected ' + $models.Count + ' models:');" ^
  "  Write-Host '';" ^
  "  for ($i = 0; $i -lt $models.Count; $i++) {" ^
  "    Write-Host ('  [{0}] {1}' -f ($i + 1), $models[$i]);" ^
  "  };" ^
  "  Write-Host '';" ^
  "  do {" ^
  "    $choice = Read-Host 'Select model number';" ^
  "    $number = 0;" ^
  "    $valid = [int]::TryParse($choice, [ref]$number) -and" ^
  "             $number -ge 1 -and" ^
  "             $number -le $models.Count;" ^
  "    if (-not $valid) {" ^
  "      Write-Host 'Please enter a valid model number.' -ForegroundColor Yellow;" ^
  "    };" ^
  "  } until ($valid);" ^
  "  $selectedIndex = $number - 1;" ^
  "  $selected = $models[$selectedIndex];" ^
  "};" ^
  "$selectedObject = $modelObjects[$selectedIndex];" ^
  "$context = 0L;" ^
  "foreach ($propertyName in @('max_model_len', 'max_context_length', 'context_length')) {" ^
  "  $property = $selectedObject.PSObject.Properties[$propertyName];" ^
  "  if ($null -ne $property -and $null -ne $property.Value) {" ^
  "    $candidate = 0L;" ^
  "    if ([long]::TryParse(([string]$property.Value), [ref]$candidate) -and $candidate -gt 0) {" ^
  "      $context = $candidate;" ^
  "      break;" ^
  "    };" ^
  "  };" ^
  "};" ^
  "if ($context -le 0) {" ^
  "  $fallback = 0L;" ^
  "  if (-not [long]::TryParse($env:FALLBACK_CONTEXT_TOKENS, [ref]$fallback) -or $fallback -le 0) {" ^
  "    Write-Host 'ERROR: FALLBACK_CONTEXT_TOKENS is invalid.' -ForegroundColor Red;" ^
  "    exit 4;" ^
  "  };" ^
  "  $context = $fallback;" ^
  "  Write-Host ('Context length was not advertised; using fallback: ' + $context.ToString('N0'));" ^
  "} else {" ^
  "  Write-Host ('Advertised context length: ' + $context.ToString('N0'));" ^
  "};" ^
  "[System.IO.File]::WriteAllText($env:MODEL_FILE, $selected);" ^
  "[System.IO.File]::WriteAllText($env:CONTEXT_FILE, [string]$context);"

set "DISCOVERY_EXIT=%ERRORLEVEL%"

if not "%DISCOVERY_EXIT%"=="0" (
    if exist "%MODEL_FILE%" del /q "%MODEL_FILE%" >nul 2>&1
    if exist "%CONTEXT_FILE%" del /q "%CONTEXT_FILE%" >nul 2>&1
    echo.
    echo Claude Code was not started.
    exit /b %DISCOVERY_EXIT%
)

if not exist "%MODEL_FILE%" (
    echo.
    echo ERROR: Model discovery completed without returning a selected model.
    if exist "%CONTEXT_FILE%" del /q "%CONTEXT_FILE%" >nul 2>&1
    exit /b 4
)

if not exist "%CONTEXT_FILE%" (
    echo.
    echo ERROR: Model discovery completed without returning a context length.
    if exist "%MODEL_FILE%" del /q "%MODEL_FILE%" >nul 2>&1
    exit /b 4
)

set /p "CLAUDE_DGX_MODEL="<"%MODEL_FILE%"
set /p "CLAUDE_DGX_CONTEXT="<"%CONTEXT_FILE%"

del /q "%MODEL_FILE%" >nul 2>&1
del /q "%CONTEXT_FILE%" >nul 2>&1

if not defined CLAUDE_DGX_MODEL (
    echo.
    echo ERROR: The selected model ID was empty.
    exit /b 5
)

if not defined CLAUDE_DGX_CONTEXT (
    echo.
    echo ERROR: The selected model context length was empty.
    exit /b 5
)


REM ============================================================================
REM Route Claude Code and subagents to the selected local llama.cpp model
REM ============================================================================

set "ANTHROPIC_MODEL=%CLAUDE_DGX_MODEL%"
set "ANTHROPIC_DEFAULT_FABLE_MODEL=%CLAUDE_DGX_MODEL%"
set "ANTHROPIC_DEFAULT_OPUS_MODEL=%CLAUDE_DGX_MODEL%"
set "ANTHROPIC_DEFAULT_SONNET_MODEL=%CLAUDE_DGX_MODEL%"
set "ANTHROPIC_DEFAULT_HAIKU_MODEL=%CLAUDE_DGX_MODEL%"

set "CLAUDE_CODE_SUBAGENT_MODEL=%CLAUDE_DGX_MODEL%"

set "ANTHROPIC_CUSTOM_MODEL_OPTION=%CLAUDE_DGX_MODEL%"
set "ANTHROPIC_CUSTOM_MODEL_OPTION_NAME=Muse Glimmer local - %CLAUDE_DGX_MODEL%"


REM ============================================================================
REM Hard context-window protection for unattended operation
REM ============================================================================

set "CLAUDE_CODE_MAX_CONTEXT_TOKENS=%CLAUDE_DGX_CONTEXT%"
set "CLAUDE_CODE_AUTO_COMPACT_WINDOW=%CLAUDE_DGX_CONTEXT%"
set "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=%DGX_AUTOCOMPACT_PERCENT%"
set "CLAUDE_CODE_MAX_OUTPUT_TOKENS=%DGX_MAX_OUTPUT_TOKENS%"

set /a "AUTO_COMPACT_TRIGGER_TOKENS=(CLAUDE_DGX_CONTEXT * DGX_AUTOCOMPACT_PERCENT) / 100"


REM ============================================================================
REM Locate the real Claude Code executable
REM ============================================================================

set "REAL_CLAUDE="

for /f "delims=" %%I in ('where.exe claude.exe 2^>nul') do (
    if /I not "%%~fI"=="%~f0" (
        set "REAL_CLAUDE=%%~fI"
        goto :found_claude
    )
)

for /f "delims=" %%I in ('where.exe claude.cmd 2^>nul') do (
    if /I not "%%~fI"=="%~f0" (
        set "REAL_CLAUDE=%%~fI"
        goto :found_claude
    )
)

for /f "delims=" %%I in ('where.exe claude 2^>nul') do (
    if /I not "%%~fI"=="%~f0" (
        set "REAL_CLAUDE=%%~fI"
        goto :found_claude
    )
)

if exist "%USERPROFILE%\.local\bin\claude.exe" (
    set "REAL_CLAUDE=%USERPROFILE%\.local\bin\claude.exe"
    goto :found_claude
)

if exist "%APPDATA%\npm\claude.cmd" (
    set "REAL_CLAUDE=%APPDATA%\npm\claude.cmd"
    goto :found_claude
)

:found_claude

if not defined REAL_CLAUDE (
    echo.
    echo ERROR: Claude Code was not found.
    echo.
    echo Checked:
    echo   PATH
    echo   %USERPROFILE%\.local\bin\claude.exe
    echo   %APPDATA%\npm\claude.cmd
    echo.
    exit /b 6
)


REM ============================================================================
REM Verify Claude Code supports custom-model context overrides
REM ============================================================================

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference = 'Stop';" ^
  "$minimum = [version]'2.1.193';" ^
  "try {" ^
  "  $raw = (& $env:REAL_CLAUDE --version 2>&1 | Out-String).Trim();" ^
  "} catch {" ^
  "  Write-Host 'ERROR: Could not determine the Claude Code version.' -ForegroundColor Red;" ^
  "  Write-Host ('       ' + $_.Exception.Message);" ^
  "  exit 7;" ^
  "};" ^
  "$match = [regex]::Match($raw, '\d+\.\d+\.\d+');" ^
  "if (-not $match.Success) {" ^
  "  Write-Host ('ERROR: Could not parse Claude Code version from: ' + $raw) -ForegroundColor Red;" ^
  "  exit 7;" ^
  "};" ^
  "$version = [version]$match.Value;" ^
  "Write-Host ('Claude Code version: ' + $version);" ^
  "if ($version -lt $minimum) {" ^
  "  Write-Host '';" ^
  "  Write-Host ('ERROR: Claude Code ' + $minimum + ' or newer is required.') -ForegroundColor Red;" ^
  "  Write-Host 'Run: claude update';" ^
  "  exit 7;" ^
  "};"

set "VERSION_EXIT=%ERRORLEVEL%"

if not "%VERSION_EXIT%"=="0" (
    echo.
    echo Claude Code was not started because the installed version cannot
    echo reliably enforce the custom model context window.
    exit /b %VERSION_EXIT%
)


REM ============================================================================
REM Speech-to-text intentionally disabled in this launcher
REM ============================================================================

set "HANDY_EXE="
set "HANDY_STATUS=Disabled"


REM ============================================================================
REM Display startup configuration
REM ============================================================================

echo.
echo Starting Claude Code
echo =============================================================================
echo   Model:          %CLAUDE_DGX_MODEL%
echo   Endpoint:       %ANTHROPIC_BASE_URL%/v1/messages
echo   Context limit:  %CLAUDE_CODE_MAX_CONTEXT_TOKENS% tokens
echo   Auto-compact:   %CLAUDE_AUTOCOMPACT_PCT_OVERRIDE%%% at about %AUTO_COMPACT_TRIGGER_TOKENS% tokens
echo   Max response:   %CLAUDE_CODE_MAX_OUTPUT_TOKENS% tokens
echo   Effort:         ultracode
echo   Permissions:    bypassed - unrestricted
echo   CLI:            %REAL_CLAUDE%
echo   Speech:         %HANDY_STATUS%
echo =============================================================================
echo.

if not defined HANDY_EXE (
    echo NOTE: Handy local speech-to-text was not found.
    echo.
    echo Claude Code will still start normally.
    echo For free speech-to-text, install Handy and configure a push-to-talk key.
    echo Recommended shortcut: Ctrl+Alt+Space
    echo.
)

echo CONTEXT SAFETY: Claude Code will compact at approximately
echo %AUTO_COMPACT_TRIGGER_TOKENS% tokens rather than approaching the
echo %CLAUDE_CODE_MAX_CONTEXT_TOKENS%-token llama.cpp slot limit.
echo.
echo WARNING: Claude Code can modify, delete, and execute files without approval.
echo.


REM ============================================================================
REM Start Claude Code
REM ============================================================================

call "%REAL_CLAUDE%" ^
  --model "%CLAUDE_DGX_MODEL%" ^
  --effort ultracode ^
  --dangerously-skip-permissions ^
  %*

set "EXIT_CODE=%ERRORLEVEL%"

echo.
echo Claude Code exited with code %EXIT_CODE%.
echo.

endlocal & exit /b %EXIT_CODE%