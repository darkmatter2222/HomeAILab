@echo off
setlocal EnableExtensions
REM Load lab host IPs + router key from .env (harness\.env or the repo root .env).
call "%~dp0..\load-env.bat"

REM ============================================================================
REM Claude Code -> LOCAL GPU ROUTER on Databrick
REM
REM GO-FORWARD ROUTER CONTRACT
REM FULL 262,144-TOKEN CONTEXT / THINKING OFF
REM
REM Router host:
REM   Databrick LAN IP : ${HOST_3090}
REM   Router API port  : 8001
REM
REM Routing priority:
REM   priority 10 : RedPCv2 RTX 5090   (vLLM,     cap 1, host port 8201)
REM   priority 20 : Databrick RTX 3090 (llama.cpp, cap 1, host port 8101)
REM   priority 30 : DGX Spark GB10     (ds4,       cap 3, host port 8401)
REM
REM Router API range is 8001-8009 because host port 8000 is reserved by Portainer.
REM ============================================================================

REM ---- router endpoint ----
set "QWEN_ROUTER_URL=http://%HOST_3090%:8001"
set "ANTHROPIC_BASE_URL=%QWEN_ROUTER_URL%"

REM Keep the configured local-router token available.
REM If the router currently runs without auth, the extra Authorization header is harmless
REM as long as the router ignores unknown bearer tokens.
set "QWEN_ROUTER_API_KEY=%ROUTER_API_KEY%"
set "ANTHROPIC_AUTH_TOKEN=%QWEN_ROUTER_API_KEY%"

REM Stable public router alias. /v1/models is still queried and this alias is used
REM only if the router advertises it; otherwise the first advertised model is selected.
set "PREFERRED_ROUTER_MODEL=local-coding"

REM ============================================================================
REM FULL 262K CONTEXT
REM ============================================================================
REM The router's coding pool is configured for endpoints with up to 262,144 tokens.
REM Claude Code uses this explicit unknown/custom-model context setting.
REM
REM Total model context : 262,144
REM Auto-compact at     : 245,760
REM Reserved headroom   : 16,384
REM Max response        : 8,192
REM ============================================================================

set "CLAUDE_DGX_CONTEXT=262144"
set "CLAUDE_CODE_MAX_CONTEXT_TOKENS=262144"

REM Retain 16K headroom before the hard 262K backend limit.
set "CLAUDE_CODE_AUTO_COMPACT_WINDOW=245760"

REM Response budget.
set "CLAUDE_CODE_MAX_OUTPUT_TOKENS=8192"

REM Do not impose a second percentage-based compaction threshold.
set "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE="

REM Keep compaction ENABLED.
set "DISABLE_COMPACT="
set "DISABLE_AUTO_COMPACT="

REM Do not apply a smaller unknown-model safety window.
set "CLAUDE_CODE_DISABLE_UNKNOWN_MODEL_WINDOW_ENFORCEMENT="

REM Thinking OFF.
set "MAX_THINKING_TOKENS=0"
set "CLAUDE_CODE_DISABLE_THINKING=1"

REM Keep large MCP results bounded.
set "MAX_MCP_OUTPUT_TOKENS=8000"

REM ============================================================================
REM LONG-RUN / SLOW-LOCAL-MODEL TIMEOUTS
REM ============================================================================

REM 21,600,000 ms = 6 hours per model/API request.
set "API_TIMEOUT_MS=21600000"

REM Each retry gets a fresh API timeout.
set "CLAUDE_CODE_MAX_RETRIES=10"

REM Background/subagent stall watchdog: 6 hours.
set "CLAUDE_ASYNC_AGENT_STALL_TIMEOUT_MS=21600000"

REM Streaming idle watchdog: 2 hours.
set "CLAUDE_STREAM_IDLE_TIMEOUT_MS=7200000"
set "CLAUDE_ENABLE_BYTE_WATCHDOG=1"

REM Foreground Bash max: 10 minutes.
set "BASH_DEFAULT_TIMEOUT_MS=600000"
set "BASH_MAX_TIMEOUT_MS=600000"

REM MCP timeouts.
set "MCP_TIMEOUT=120000"
set "MCP_TOOL_TIMEOUT=100000000"

REM Temporary discovery file.
set "MODEL_FILE=%TEMP%\claude-router-model-%RANDOM%-%RANDOM%.tmp"


REM ============================================================================
REM VERIFY THE NEW ROUTER AND DISCOVER THE PUBLIC MODEL
REM ============================================================================

echo.
echo =============================================================================
echo LOCAL GPU ROUTER MODE
echo =============================================================================
echo   Router       : %ANTHROPIC_BASE_URL%
echo   Context      : %CLAUDE_DGX_CONTEXT%
echo   Compact at   : %CLAUDE_CODE_AUTO_COMPACT_WINDOW%
echo   Max response : %CLAUDE_CODE_MAX_OUTPUT_TOKENS%
echo   Routing      : 5090 -^> 3090 -^> DGX Spark
echo   Capacities   : 1 / 1 / 3
echo   Thinking     : OFF
echo =============================================================================
echo.

echo Probing required router APIs:
echo   %ANTHROPIC_BASE_URL%/health
echo   %ANTHROPIC_BASE_URL%/v1/models
echo.
echo Optional backend status:
echo   %ANTHROPIC_BASE_URL%/admin/endpoints
echo.

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference = 'Stop';" ^
  "$url = $env:ANTHROPIC_BASE_URL.TrimEnd('/');" ^
  "$headers = @{ Authorization = 'Bearer ' + $env:ANTHROPIC_AUTH_TOKEN };" ^
  "" ^
  "try {" ^
  "  $health = Invoke-RestMethod -Uri ($url + '/health') -Method Get -Headers $headers -TimeoutSec 30;" ^
  "} catch {" ^
  "  Write-Host '';" ^
  "  Write-Host ('ERROR: router is unreachable or unhealthy: ' + $url) -ForegroundColor Red;" ^
  "  Write-Host ('       ' + $_.Exception.Message) -ForegroundColor Yellow;" ^
  "  exit 2;" ^
  "};" ^
  "Write-Host 'Router health: OK' -ForegroundColor Green;" ^
  "" ^
  "try {" ^
  "  $eps = Invoke-RestMethod -Uri ($url + '/admin/endpoints') -Method Get -Headers $headers -TimeoutSec 10;" ^
  "  Write-Host '';" ^
  "  Write-Host 'Registered endpoints:';" ^
  "  $items = @();" ^
  "  if ($eps -is [System.Array]) { $items = @($eps) }" ^
  "  elseif ($null -ne $eps.endpoints) { $items = @($eps.endpoints) }" ^
  "  elseif ($null -ne $eps.data) { $items = @($eps.data) };" ^
  "  foreach ($e in $items) {" ^
  "    $id = if ($null -ne $e.id) { $e.id } elseif ($null -ne $e.name) { $e.name } else { '?' };" ^
  "    $state = if ($null -ne $e.health) { $e.health } elseif ($null -ne $e.state) { $e.state } elseif ($null -ne $e.healthy) { $e.healthy } else { '?' };" ^
  "    $cap = if ($null -ne $e.capacity) { $e.capacity } elseif ($null -ne $e.static_capacity) { $e.static_capacity } else { '?' };" ^
  "    $inflight = if ($null -ne $e.inflight) { $e.inflight } else { '?' };" ^
  "    $prio = if ($null -ne $e.priority) { $e.priority } else { '?' };" ^
  "    Write-Host ('  ' + $id + '  state=' + $state + '  priority=' + $prio + '  cap=' + $cap + '  inflight=' + $inflight);" ^
  "  }" ^
  "} catch {" ^
  "  Write-Host 'Admin endpoint status unavailable (non-fatal).' -ForegroundColor DarkGray;" ^
  "};" ^
  "" ^
  "try {" ^
  "  $response = Invoke-RestMethod -Uri ($url + '/v1/models') -Method Get -Headers $headers -TimeoutSec 30;" ^
  "} catch {" ^
  "  Write-Host '';" ^
  "  Write-Host ('ERROR: router /v1/models failed: ' + $url) -ForegroundColor Red;" ^
  "  Write-Host ('       ' + $_.Exception.Message) -ForegroundColor Yellow;" ^
  "  exit 3;" ^
  "};" ^
  "$models = @($response.data | Where-Object { $null -ne $_.id -and ([string]$_.id).Trim() } | ForEach-Object { ([string]$_.id).Trim() });" ^
  "if ($models.Count -eq 0) {" ^
  "  Write-Host 'ERROR: router returned no model IDs.' -ForegroundColor Red;" ^
  "  exit 4;" ^
  "};" ^
  "$preferred = $env:PREFERRED_ROUTER_MODEL;" ^
  "$selected = $null;" ^
  "if ($models -contains $preferred) {" ^
  "  $selected = $preferred;" ^
  "  Write-Host '';" ^
  "  Write-Host ('Using router alias: ' + $selected) -ForegroundColor Green;" ^
  "} elseif ($models.Count -eq 1) {" ^
  "  $selected = $models[0];" ^
  "  Write-Host '';" ^
  "  Write-Host ('Router alias not advertised; using only available model: ' + $selected) -ForegroundColor Yellow;" ^
  "} else {" ^
  "  Write-Host '';" ^
  "  Write-Host ('Router advertises ' + $models.Count + ' models:');" ^
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
    echo ERROR: Router model discovery did not return a model.
    exit /b 5
)

set /p "CLAUDE_DGX_MODEL="<"%MODEL_FILE%"
del /q "%MODEL_FILE%" >nul 2>&1

if not defined CLAUDE_DGX_MODEL (
    echo.
    echo ERROR: Selected router model ID was empty.
    exit /b 6
)


REM ============================================================================
REM ROUTE ALL CLAUDE CODE MODEL ROLES THROUGH THE PUBLIC ROUTER MODEL
REM ============================================================================

set "ANTHROPIC_MODEL=%CLAUDE_DGX_MODEL%"
set "ANTHROPIC_DEFAULT_FABLE_MODEL=%CLAUDE_DGX_MODEL%"
set "ANTHROPIC_DEFAULT_OPUS_MODEL=%CLAUDE_DGX_MODEL%"
set "ANTHROPIC_DEFAULT_SONNET_MODEL=%CLAUDE_DGX_MODEL%"
set "ANTHROPIC_DEFAULT_HAIKU_MODEL=%CLAUDE_DGX_MODEL%"

set "CLAUDE_CODE_SUBAGENT_MODEL=%CLAUDE_DGX_MODEL%"

set "ANTHROPIC_CUSTOM_MODEL_OPTION=%CLAUDE_DGX_MODEL%"
set "ANTHROPIC_CUSTOM_MODEL_OPTION_NAME=Local GPU Router - %CLAUDE_DGX_MODEL%"


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
    exit /b 7
)


REM ============================================================================
REM DISPLAY FINAL CONFIGURATION
REM ============================================================================

echo.
echo Starting Claude Code
echo =============================================================================
echo   Model:          %CLAUDE_DGX_MODEL%
echo   Endpoint:       %ANTHROPIC_BASE_URL%/v1/messages
echo   Router:         %ANTHROPIC_BASE_URL%
echo   Routing:        5090 ^(10^) -^> 3090 ^(20^) -^> Spark ^(30^)
echo   Capacities:     5090=1, 3090=1, Spark=3
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
echo   Router auth:    configured
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
