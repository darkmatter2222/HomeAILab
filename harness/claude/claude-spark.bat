@echo off
setlocal EnableExtensions
REM Load lab host IPs + router key from .env (harness\.env or the repo root .env).
call "%~dp0..\load-env.bat"

REM ============================================================================
REM Claude Code -> DIRECT DGX SPARK (GB10 / Blackwell) — Flash-Next 180B MoE
REM DIRECT BACKEND (router bypass)
REM
REM FULL 262,144-TOKEN CONTEXT / THINKING OFF
REM
REM Direct backend:
REM   DGX Spark (GB10)
REM   Host         : ${HOST_DGXSPARK}
REM   Port         : 8401  (port contract: 8400-8499 = vision)
REM   Engine       : ds4 (C/CUDA fork) serving Qwen3.8-Flash-Next 180B MoE
REM   Capability   : native vision (embedded Qwen tower, no mmproj)
REM   Caveat       : ~60-120 s cold TTFT (SSD-PLE prefill). The 120 s probe
REM                   timeout below gives the slow prefill 10x more room to emit its
REM                   first byte, matching the router's response_header_timeout.
REM ============================================================================

REM ---- direct DGX Spark Flash-Next endpoint ----
REM Do NOT hard-code one host mapping here. The probe below will select the
REM first reachable endpoint.
set "QWEN_SPARK_URL="
set "ANTHROPIC_BASE_URL="

REM Flash-Next runs without API-key enforcement. Claude Code expects an
REM Anthropic auth-token variable when using ANTHROPIC_BASE_URL, so a local
REM placeholder keeps the client happy.
set "ANTHROPIC_AUTH_TOKEN=local-spark"

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
set "CLAUDE_CODE_AUTO_COMPACT_WINDOW=245760"
set "CLAUDE_CODE_MAX_OUTPUT_TOKENS=8192"
set "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE="
set "DISABLE_COMPACT="
set "DISABLE_AUTO_COMPACT="
set "CLAUDE_CODE_DISABLE_UNKNOWN_MODEL_WINDOW_ENFORCEMENT="

REM Thinking OFF (ds4 chat template forces enable_thinking=false).
set "MAX_THINKING_TOKENS=0"
set "CLAUDE_CODE_DISABLE_THINKING=1"

REM Keep large MCP results bounded without wasting the full context.
set "MAX_MCP_OUTPUT_TOKENS=8000"

REM ============================================================================
REM LONG-RUN / SLOW-LOCAL-MODEL TIMEOUTS
REM ============================================================================
set "API_TIMEOUT_MS=216000000"
set "CLAUDE_CODE_MAX_RETRIES=10"
set "CLAUDE_ASYNC_AGENT_STALL_TIMEOUT_MS=216000000"
set "CLAUDE_STREAM_IDLE_TIMEOUT_MS=72000000"
REM Flash-Next can spend minutes in prefill without emitting response bytes.
REM Disable Claude Code's independent stream/first-byte watchdogs so a healthy
REM Spark request is governed by API_TIMEOUT_MS rather than being abandoned early.
set "API_FORCE_IDLE_TIMEOUT=0"
set "CLAUDE_ENABLE_BYTE_WATCHDOG=0"
set "CLAUDE_ENABLE_STREAM_WATCHDOG=0"
set "CLAUDE_STREAM_FIRST_BYTE_TIMEOUT_MS="
set "CLAUDE_BYTE_STREAM_IDLE_TIMEOUT_MS="
set "BASH_DEFAULT_TIMEOUT_MS=6000000"
set "BASH_MAX_TIMEOUT_MS=6000000"
set "MCP_TIMEOUT=1200000"
set "MCP_TOOL_TIMEOUT=1000000000"

REM Temporary model-discovery file.
set "MODEL_FILE=%TEMP%\claude-spark-model-%RANDOM%-%RANDOM%.tmp"
set "ENDPOINT_FILE=%TEMP%\claude-spark-endpoint-%RANDOM%-%RANDOM%.tmp"

REM ============================================================================
REM AUTO-DETECT DIRECT DGX SPARK ENDPOINT AND DISCOVER THE MODEL
REM ============================================================================
REM Probe likely mappings in preferred order (the Spark's /health is a real
REM endpoint; the 1200 s timeout covers the cold SSD-PLE prefill):
REM   1) ${HOST_DGXSPARK}:8401  DGX Spark published port
REM   2) 127.0.0.1:8401      localhost fallback
REM ============================================================================

echo.
echo =============================================================================
echo DIRECT DGX SPARK MODE  ^(direct backend, no router^)
echo =============================================================================
echo   GPU          : DGX Spark GB10
echo   Model        : Qwen3.8-Flash-Next 180B MoE (native vision)
echo   Host         : %HOST_DGXSPARK%
echo   Port         : 8401
echo   Context      : %CLAUDE_DGX_CONTEXT%
echo   Compact at   : %CLAUDE_CODE_AUTO_COMPACT_WINDOW%
echo   Max response : %CLAUDE_CODE_MAX_OUTPUT_TOKENS%
echo   Thinking     : OFF
echo   Cold start   : ~60-120 s TTFT (SSD-PLE prefill)
echo =============================================================================
echo.
echo Searching for reachable DGX Spark Flash-Next endpoint...
echo.

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference = 'SilentlyContinue';" ^
  "$candidates = @(" ^
  "  ('http://' + $env:HOST_DGXSPARK + ':8401')," ^
  "  'http://127.0.0.1:8401'" ^
  ");" ^
  "$selected = $null;" ^
  "foreach ($candidate in $candidates) {" ^
  "  Write-Host ('  probing ' + $candidate + '/health ...') -NoNewline;" ^
  "  try {" ^
  "    $r = Invoke-WebRequest -Uri ($candidate + '/health') -Method Get -TimeoutSec 1200 -UseBasicParsing;" ^
  "    if ($r.StatusCode -ge 200 -and $r.StatusCode -lt 300) {" ^
  "      Write-Host ' OK' -ForegroundColor Green;" ^
  "      $selected = $candidate;" ^
  "      break;" ^
  "    }" ^
  "  } catch [System.Net.HttpListenerException] {" ^
  "    Write-Host ' no' -ForegroundColor DarkGray;" ^
  "  } catch {" ^
  "    Write-Host ' no' -ForegroundColor DarkGray;" ^
  "  }" ^
  "};" ^
  "if (-not $selected) {" ^
  "  Write-Host '';" ^
  "  Write-Host 'ERROR: No reachable DGX Spark Flash-Next endpoint was found.' -ForegroundColor Red;" ^
  "  Write-Host ('Checked ' + $env:HOST_DGXSPARK + ':8401 and localhost:8401.') -ForegroundColor Yellow;" ^
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

set /p "QWEN_SPARK_URL="<"%ENDPOINT_FILE%"
del /q "%ENDPOINT_FILE%" >nul 2>&1
set "ANTHROPIC_BASE_URL=%QWEN_SPARK_URL%"

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
  "  $null = Invoke-RestMethod -Uri ($url + '/health') -Method Get -TimeoutSec 1200;" ^
  "} catch {" ^
  "  Write-Host '';" ^
  "  Write-Host ('ERROR: DGX Spark Flash-Next became unreachable: ' + $url) -ForegroundColor Red;" ^
  "  Write-Host ('       ' + $_.Exception.Message) -ForegroundColor Yellow;" ^
  "  exit 2;" ^
  "};" ^
  "Write-Host 'DGX Spark Flash-Next health: OK';" ^
  "" ^
  "try {" ^
  "  $response = Invoke-RestMethod -Uri ($url + '/v1/models') -Method Get -Headers $headers -TimeoutSec 1200;" ^
  "} catch {" ^
  "  Write-Host '';" ^
  "  Write-Host ('ERROR: DGX Spark /v1/models unreachable: ' + $url) -ForegroundColor Red;" ^
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
REM ROUTE ALL CLAUDE CODE MODEL ROLES TO THE DIRECT SPARK MODEL
REM ============================================================================

set "ANTHROPIC_MODEL=%CLAUDE_DGX_MODEL%"
set "ANTHROPIC_DEFAULT_FABLE_MODEL=%CLAUDE_DGX_MODEL%"
set "ANTHROPIC_DEFAULT_OPUS_MODEL=%CLAUDE_DGX_MODEL%"
set "ANTHROPIC_DEFAULT_SONNET_MODEL=%CLAUDE_DGX_MODEL%"
set "ANTHROPIC_DEFAULT_HAIKU_MODEL=%CLAUDE_DGX_MODEL%"

set "CLAUDE_CODE_SUBAGENT_MODEL=%CLAUDE_DGX_MODEL%"

set "ANTHROPIC_CUSTOM_MODEL_OPTION=%CLAUDE_DGX_MODEL%"
set "ANTHROPIC_CUSTOM_MODEL_OPTION_NAME=DGX Spark Flash-Next Direct - %CLAUDE_DGX_MODEL%"


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
echo   Endpoint:       %ANTHROPIC_BASE_URL%/v1/chat/completions
echo   Backend:        DGX SPARK FLASH-NEXT DIRECT - NO ROUTER
echo   Direct URL:     %ANTHROPIC_BASE_URL%
echo   Total context:  %CLAUDE_CODE_MAX_CONTEXT_TOKENS% tokens
echo   Compact window: %CLAUDE_CODE_AUTO_COMPACT_WINDOW% tokens
echo   Max response:   %CLAUDE_CODE_MAX_OUTPUT_TOKENS% tokens
echo   Thinking:       OFF
echo   Image input:    NATIVE VISION (still-image)
echo   MCP tool cap:   %MAX_MCP_OUTPUT_TOKENS% tokens
echo   API timeout:    60 hours/request
echo   First-byte WD:  OFF (slow Spark prefill allowed)
echo   Stream WD:      OFF (local model profile)
echo   Agent stall:    60 hours
echo   Stream idle:    20 hours
echo   Bash timeout:   100 minutes max/foreground
echo   Permissions:    bypassed - unrestricted
echo   CLI:            %REAL_CLAUDE%
echo =============================================================================
echo.
echo EXPECTED /context:
echo   Total context should be approximately 262.1k tokens.
echo   Auto-compact window should be approximately 245.8k tokens.
echo   NOTE: cold-start TTFT is ~60-120 s (SSD-PLE prefill); first
echo   response will be slow until the page cache is warm.
echo.

echo WARNING: Claude Code can modify, delete, and execute files without approval.
echo.


REM ============================================================================
REM START CLAUDE CODE
REM ============================================================================

REM Image reads are LEFT ENABLED on the Spark — Flash-Next natively accepts
REM still-image input (max 4 images / 10 MiB each), so Claude Code's Read tool
REM can feed them to the embedded Qwen vision tower.
call "%REAL_CLAUDE%" ^
  --model "%CLAUDE_DGX_MODEL%" ^
  --dangerously-skip-permissions ^
  %*

set "EXIT_CODE=%ERRORLEVEL%"

echo.
echo Claude Code exited with code %EXIT_CODE%.
echo.

endlocal & exit /b %EXIT_CODE%
