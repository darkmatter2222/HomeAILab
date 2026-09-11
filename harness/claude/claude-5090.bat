@echo off
setlocal EnableExtensions
REM Load lab host IPs + router key from .env (harness\.env or the repo root .env).
call "%~dp0..\load-env.bat"

REM ============================================================================
REM Claude Code -> DIRECT RTX 5090 vLLM
REM TEMPORARY ROUTER BYPASS
REM
REM FULL 262,144-TOKEN CONTEXT / THINKING OFF
REM
REM Direct backend:
REM   RedPCv2 RTX 5090
REM   LAN IP       : ${HOST_5090}
REM   Published    : 8201
REM   vLLM internal: 8006
REM   Model alias  : qwen3.8
REM ============================================================================

REM ---- direct RTX 5090 vLLM endpoint ----
REM Do NOT hard-code one host mapping here. Docker Desktop / WSL networking can
REM expose the published port differently depending on how the stack was started.
REM The probe below will select the first reachable endpoint.
set "QWEN_5090_URL="
set "ANTHROPIC_BASE_URL="

REM vLLM is currently running without API-key enforcement.
REM Claude Code expects an Anthropic auth-token variable to exist when using
REM ANTHROPIC_BASE_URL, so provide a harmless local placeholder.
set "ANTHROPIC_AUTH_TOKEN=local-5090"

REM ============================================================================
REM FULL 262K CONTEXT
REM ============================================================================
REM qwen3.8 is a custom/unrecognized model ID behind ANTHROPIC_BASE_URL.
REM Claude Code therefore honors CLAUDE_CODE_MAX_CONTEXT_TOKENS directly.
REM
REM Total model context : 262,144
REM Auto-compact at     : 245,760
REM Reserved headroom   : 16,384
REM Max response        : 8,192
REM ============================================================================

set "CLAUDE_DGX_CONTEXT=262144"
set "CLAUDE_CODE_MAX_CONTEXT_TOKENS=262144"

REM Run almost the full 262K window while retaining 16K of headroom for
REM response generation / bookkeeping before the hard backend limit.
set "CLAUDE_CODE_AUTO_COMPACT_WINDOW=245760"

REM Response budget.
set "CLAUDE_CODE_MAX_OUTPUT_TOKENS=8192"

REM Do not impose a second percentage-based compaction threshold.
set "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE="

REM IMPORTANT: leave compaction ENABLED.
set "DISABLE_COMPACT="
set "DISABLE_AUTO_COMPACT="

REM Do not apply any unknown-model safety window smaller than the explicit
REM 262,144-token value above.
set "CLAUDE_CODE_DISABLE_UNKNOWN_MODEL_WINDOW_ENFORCEMENT="

REM Thinking OFF.
set "MAX_THINKING_TOKENS=0"
set "CLAUDE_CODE_DISABLE_THINKING=1"

REM Keep large MCP results bounded without wasting the full context.
set "MAX_MCP_OUTPUT_TOKENS=8000"

REM ============================================================================
REM LONG-RUN / SLOW-LOCAL-MODEL TIMEOUTS
REM ============================================================================
REM Claude Code API request timeout.
REM 21,600,000 ms = 6 hours per individual model/API request.
set "API_TIMEOUT_MS=21600000"

REM Keep retry behavior explicit. Each retry gets a fresh API timeout.
set "CLAUDE_CODE_MAX_RETRIES=10"

REM Background/subagent stall watchdog.
REM Allow a background agent to go up to 6 hours without a stream event.
set "CLAUDE_ASYNC_AGENT_STALL_TIMEOUT_MS=21600000"

REM Streaming idle watchdog.
REM 7,200,000 ms = 2 hours of no stream activity before considering it stalled.
set "CLAUDE_STREAM_IDLE_TIMEOUT_MS=7200000"

REM Force the byte-level watchdog on, with the extended idle window above.
set "CLAUDE_ENABLE_BYTE_WATCHDOG=1"

REM Bash tool timeout. Claude Code currently caps a foreground Bash call at
REM 600,000 ms (10 minutes), so anything longer should be started in background.
set "BASH_DEFAULT_TIMEOUT_MS=600000"
set "BASH_MAX_TIMEOUT_MS=600000"

REM MCP startup and execution timeouts.
set "MCP_TIMEOUT=120000"
set "MCP_TOOL_TIMEOUT=100000000"

REM Temporary model-discovery file.
set "MODEL_FILE=%TEMP%\claude-5090-model-%RANDOM%-%RANDOM%.tmp"


REM ============================================================================
REM AUTO-DETECT DIRECT RTX 5090 ENDPOINT AND DISCOVER THE MODEL
REM ============================================================================
REM Probe likely Docker Desktop mappings in preferred order:
REM   1) localhost:8201       new go-forward vLLM published port
REM   2) ${HOST_5090}:8201  same published port via LAN
REM   3) localhost:8006       legacy/direct published port
REM   4) ${HOST_5090}:8006  legacy/direct LAN mapping
REM ============================================================================

set "ENDPOINT_FILE=%TEMP%\claude-5090-endpoint-%RANDOM%-%RANDOM%.tmp"

echo.
echo =============================================================================
echo DIRECT RTX 5090 MODE  ^(temporary router bypass^)
echo =============================================================================
echo   GPU          : RTX 5090
echo   Runtime      : vLLM 0.27.1
echo   Context      : %CLAUDE_DGX_CONTEXT%
echo   Compact at   : %CLAUDE_CODE_AUTO_COMPACT_WINDOW%
echo   Max response : %CLAUDE_CODE_MAX_OUTPUT_TOKENS%
echo   Thinking     : OFF
echo =============================================================================
echo.
echo Searching for reachable RTX 5090 vLLM endpoint...
echo.

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference = 'SilentlyContinue';" ^
  "$candidates = @(" ^
  "  'http://127.0.0.1:8201'," ^
  "  ('http://' + $env:HOST_5090 + ':8201')," ^
  "  'http://127.0.0.1:8006'," ^
  "  ('http://' + $env:HOST_5090 + ':8006')" ^
  ");" ^
  "$selected = $null;" ^
  "foreach ($candidate in $candidates) {" ^
  "  Write-Host ('  probing ' + $candidate + '/health ...') -NoNewline;" ^
  "  try {" ^
  "    Invoke-RestMethod -Uri ($candidate + '/health') -Method Get -TimeoutSec 4 | Out-Null;" ^
  "    Write-Host ' OK' -ForegroundColor Green;" ^
  "    $selected = $candidate;" ^
  "    break;" ^
  "  } catch {" ^
  "    Write-Host ' no' -ForegroundColor DarkGray;" ^
  "  }" ^
  "};" ^
  "if (-not $selected) {" ^
  "  Write-Host '';" ^
  "  Write-Host 'ERROR: No reachable RTX 5090 vLLM endpoint was found.' -ForegroundColor Red;" ^
  "  Write-Host 'Checked localhost/LAN on ports 8201 and 8006.' -ForegroundColor Yellow;" ^
  "  exit 2;" ^
  "};" ^
  "[System.IO.File]::WriteAllText($env:ENDPOINT_FILE, $selected);"

set "ENDPOINT_EXIT=%ERRORLEVEL%"
if not "%ENDPOINT_EXIT%"=="0" (
    if exist "%ENDPOINT_FILE%" del /q "%ENDPOINT_FILE%" >nul 2>&1
    echo.
    echo Run this command to inspect Docker port publication:
    echo   docker ps --format "table {{.Names}}\t{{.Ports}}"
    echo.
    echo Claude Code was not started.
    exit /b %ENDPOINT_EXIT%
)

set /p "QWEN_5090_URL="<"%ENDPOINT_FILE%"
del /q "%ENDPOINT_FILE%" >nul 2>&1
set "ANTHROPIC_BASE_URL=%QWEN_5090_URL%"

echo.
echo Selected backend: %ANTHROPIC_BASE_URL%
echo.
echo Probing:
echo   %ANTHROPIC_BASE_URL%/health
echo   %ANTHROPIC_BASE_URL%/v1/models
echo.

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference = 'Stop';" ^
  "$url = $env:ANTHROPIC_BASE_URL.TrimEnd('/');" ^
  "$headers = @{ Authorization = 'Bearer ' + $env:ANTHROPIC_AUTH_TOKEN };" ^
  "" ^
  "try {" ^
  "  $null = Invoke-RestMethod -Uri ($url + '/health') -Method Get -TimeoutSec 60;" ^
  "} catch {" ^
  "  Write-Host '';" ^
  "  Write-Host ('ERROR: RTX 5090 vLLM became unreachable: ' + $url) -ForegroundColor Red;" ^
  "  Write-Host ('       ' + $_.Exception.Message) -ForegroundColor Yellow;" ^
  "  exit 2;" ^
  "};" ^
  "Write-Host 'RTX 5090 vLLM health: OK';" ^
  "" ^
  "try {" ^
  "  $response = Invoke-RestMethod -Uri ($url + '/v1/models') -Method Get -Headers $headers -TimeoutSec 60;" ^
  "} catch {" ^
  "  Write-Host '';" ^
  "  Write-Host ('ERROR: RTX 5090 /v1/models unreachable: ' + $url) -ForegroundColor Red;" ^
  "  Write-Host ('       ' + $_.Exception.Message) -ForegroundColor Yellow;" ^
  "  exit 2;" ^
  "};" ^
  "$models = @($response.data | Where-Object { $null -ne $_.id -and ([string]$_.id).Trim() } | ForEach-Object { ([string]$_.id).Trim() });" ^
  "if ($models.Count -eq 0) {" ^
  "  Write-Host 'ERROR: vLLM returned no model IDs.' -ForegroundColor Red;" ^
  "  exit 3;" ^
  "};" ^
  "if ($models.Count -eq 1) {" ^
  "  $selected = $models[0];" ^
  "  Write-Host ('Detected model: ' + $selected);" ^
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
  "    $valid = [int]::TryParse($choice, [ref]$number) -and $number -ge 1 -and $number -le $models.Count;" ^
  "    if (-not $valid) { Write-Host 'Please enter a valid model number.' -ForegroundColor Yellow; };" ^
  "  } until ($valid);" ^
  "  $selected = $models[$number - 1];" ^
  "};" ^
  "[System.IO.File]::WriteAllText($env:MODEL_FILE, $selected);"

set "DISCOVERY_EXIT=%ERRORLEVEL%"

if not "%DISCOVERY_EXIT%"=="0" (
    if exist "%MODEL_FILE%" del /q "%MODEL_FILE%" >nul 2>&1
    echo.
    echo Claude Code was not started.
    exit /b %DISCOVERY_EXIT%
)

if not exist "%MODEL_FILE%" (
    echo.
    echo ERROR: Model discovery did not return a model.
    exit /b 4
)

set /p "CLAUDE_DGX_MODEL="<"%MODEL_FILE%"
del /q "%MODEL_FILE%" >nul 2>&1

if not defined CLAUDE_DGX_MODEL (
    echo.
    echo ERROR: Selected model ID was empty.
    exit /b 5
)


REM ============================================================================
REM ROUTE ALL CLAUDE CODE MODEL ROLES TO THE DIRECT RTX 5090 MODEL
REM ============================================================================

set "ANTHROPIC_MODEL=%CLAUDE_DGX_MODEL%"
set "ANTHROPIC_DEFAULT_FABLE_MODEL=%CLAUDE_DGX_MODEL%"
set "ANTHROPIC_DEFAULT_OPUS_MODEL=%CLAUDE_DGX_MODEL%"
set "ANTHROPIC_DEFAULT_SONNET_MODEL=%CLAUDE_DGX_MODEL%"
set "ANTHROPIC_DEFAULT_HAIKU_MODEL=%CLAUDE_DGX_MODEL%"

set "CLAUDE_CODE_SUBAGENT_MODEL=%CLAUDE_DGX_MODEL%"

set "ANTHROPIC_CUSTOM_MODEL_OPTION=%CLAUDE_DGX_MODEL%"
set "ANTHROPIC_CUSTOM_MODEL_OPTION_NAME=RTX 5090 Direct - %CLAUDE_DGX_MODEL%"


REM ============================================================================
REM LOCATE CLAUDE CODE
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
    exit /b 6
)


REM ============================================================================
REM DISPLAY FINAL CONFIGURATION
REM ============================================================================

echo.
echo Starting Claude Code
echo =============================================================================
echo   Model:          %CLAUDE_DGX_MODEL%
echo   Endpoint:       %ANTHROPIC_BASE_URL%/v1/messages
echo   Backend:        RTX 5090 DIRECT - NO ROUTER
echo   Direct URL:     %ANTHROPIC_BASE_URL%
echo   Total context:  %CLAUDE_CODE_MAX_CONTEXT_TOKENS% tokens
echo   Compact window: %CLAUDE_CODE_AUTO_COMPACT_WINDOW% tokens
echo   Max response:   %CLAUDE_CODE_MAX_OUTPUT_TOKENS% tokens
echo   Thinking:       OFF
echo   Image reads:    BLOCKED
echo   MCP tool cap:   %MAX_MCP_OUTPUT_TOKENS% tokens
echo   API timeout:    6 hours/request
echo   Agent stall:    6 hours
echo   Stream idle:    2 hours
echo   Bash timeout:   10 minutes max/foreground
echo   Permissions:    bypassed - unrestricted
echo   CLI:            %REAL_CLAUDE%
echo =============================================================================
echo.

echo EXPECTED /context:
echo   Total context should be approximately 262.1k tokens.
echo   Auto-compact window should be approximately 245.8k tokens.
echo.

echo WARNING: Claude Code can modify, delete, and execute files without approval.
echo.


REM ============================================================================
REM START CLAUDE CODE
REM ============================================================================

call "%REAL_CLAUDE%" ^
  --model "%CLAUDE_DGX_MODEL%" ^
  --dangerously-skip-permissions ^
  --disallowedTools ^
    "Read(//**/*.png)" ^
    "Read(//**/*.jpg)" ^
    "Read(//**/*.jpeg)" ^
    "Read(//**/*.gif)" ^
    "Read(//**/*.webp)" ^
    "Read(//**/*.bmp)" ^
    "Read(//**/*.tif)" ^
    "Read(//**/*.tiff)" ^
    "Read(//**/*.ico)" ^
  %*

set "EXIT_CODE=%ERRORLEVEL%"

echo.
echo Claude Code exited with code %EXIT_CODE%.
echo.

endlocal & exit /b %EXIT_CODE%

