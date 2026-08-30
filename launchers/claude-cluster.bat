@echo off
setlocal EnableExtensions

REM ============================================================================
REM Load .env (real values: ROUTER_API_KEY, HOST_DATABRICK). If the user's shell
REM already exported these, we keep those; otherwise pull them from ..\.env.
REM ============================================================================
set "REPO_ENV=%~dp0..\.env"
if not defined QWEN_ROUTER_API_KEY (
    for /f "tokens=1,* delims==" %%A in ('findstr /B "ROUTER_API_KEY=" "%REPO_ENV%" 2^>nul') do set "QWEN_ROUTER_API_KEY=%%B"
)
if not defined HOST_DATABRICK (
    for /f "tokens=1,* delims==" %%A in ('findstr /B "HOST_DATABRICK=" "%REPO_ENV%" 2^>nul') do set "HOST_DATABRICK=%%B"
)
if not defined HOST_DATABRICK set "HOST_DATABRICK=192.168.86.48"
if not defined QWEN_ROUTER_PORT set "QWEN_ROUTER_PORT=8010"

REM ============================================================================
REM Claude Code -> GPU CLUSTER via the Databrick router
REM
REM FULL 262,144-TOKEN CONTEXT / THINKING OFF
REM
REM Router priority:
REM   priority 1 : RedPCv2 RTX 5090   (vLLM,      router cap 2)
REM   priority 2 : Databrick RTX 3090 (llama.cpp, router cap 1)
REM   priority 3 : DGX Spark GB10     (vLLM,      router cap 16)
REM ============================================================================

REM ---- router (Databrick, endpoint 3, port 8010) ----
REM QWEN_ROUTER_URL / QWEN_ROUTER_API_KEY come from ..\.env (or the current environment).
set "QWEN_ROUTER_URL=http://%HOST_DATABRICK%:%QWEN_ROUTER_PORT%"
set "ANTHROPIC_BASE_URL=%QWEN_ROUTER_URL%"

REM Single API key accepted by the local router.
if not defined QWEN_ROUTER_API_KEY (
    echo ERROR: QWEN_ROUTER_API_KEY not set. Source ..\.env or export it in your shell.
    exit /b 7
)
set "ANTHROPIC_AUTH_TOKEN=%QWEN_ROUTER_API_KEY%"

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

REM Temporary model-discovery file.
set "MODEL_FILE=%TEMP%\claude-cluster-model-%RANDOM%-%RANDOM%.tmp"


REM ============================================================================
REM VERIFY THE CLUSTER ROUTER AND DISCOVER THE MODEL
REM ============================================================================

echo.
echo =============================================================================
echo GPU CLUSTER MODE  (router: 5090 -^> 3090 -^> Spark)
echo =============================================================================
echo   Router       : %ANTHROPIC_BASE_URL%
echo   Context      : %CLAUDE_DGX_CONTEXT%
echo   Compact at   : %CLAUDE_CODE_AUTO_COMPACT_WINDOW%
echo   Max response : %CLAUDE_CODE_MAX_OUTPUT_TOKENS%
echo   Routing      : 5090 first, then 3090, then Spark
echo   Thinking     : OFF
echo =============================================================================
echo.

echo Probing:
echo   %ANTHROPIC_BASE_URL%/router/status
echo   %ANTHROPIC_BASE_URL%/v1/models
echo.

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference = 'Stop';" ^
  "$url = $env:ANTHROPIC_BASE_URL.TrimEnd('/');" ^
  "$headers = @{ Authorization = 'Bearer ' + $env:ANTHROPIC_AUTH_TOKEN };" ^
  "" ^
  "try {" ^
  "  $status = Invoke-RestMethod -Uri ($url + '/router/status') -Method Get -TimeoutSec 15;" ^
  "} catch {" ^
  "  Write-Host '';" ^
  "  Write-Host ('ERROR: router is unreachable: ' + $url) -ForegroundColor Red;" ^
  "  Write-Host ('       ' + $_.Exception.Message) -ForegroundColor Yellow;" ^
  "  exit 2;" ^
  "};" ^
  "Write-Host 'Router reachable. Backends:';" ^
  "foreach ($b in $status.backends) {" ^
  "  $cap = $b.capacity;" ^
  "  $avail = $b.available;" ^
  "  $mark = 'OK';" ^
  "  if ($b.healthy -eq $false) { $mark = 'DOWN' };" ^
  "  $maxctx = $null;" ^
  "  if ($null -ne $b.max_context) { $maxctx = $b.max_context };" ^
  "  if (($null -eq $maxctx) -and ($null -ne $b.context_window)) { $maxctx = $b.context_window };" ^
  "  if (($null -eq $maxctx) -and ($null -ne $b.max_model_len)) { $maxctx = $b.max_model_len };" ^
  "  $extra = '';" ^
  "  if ($null -ne $maxctx) { $extra = ' maxctx=' + $maxctx };" ^
  "  Write-Host ('  ' + $b.name + '  prio=' + $b.priority + '  cap=' + $cap + '  avail=' + $avail + '  ' + $mark + $extra);" ^
  "};" ^
  "" ^
  "try {" ^
  "  $response = Invoke-RestMethod -Uri ($url + '/v1/models') -Method Get -Headers $headers -TimeoutSec 15;" ^
  "} catch {" ^
  "  Write-Host '';" ^
  "  Write-Host ('ERROR: router /v1/models unreachable: ' + $url) -ForegroundColor Red;" ^
  "  Write-Host ('       ' + $_.Exception.Message) -ForegroundColor Yellow;" ^
  "  exit 2;" ^
  "};" ^
  "$models = @($response.data | Where-Object { $null -ne $_.id -and ([string]$_.id).Trim() } | ForEach-Object { ([string]$_.id).Trim() });" ^
  "if ($models.Count -eq 0) {" ^
  "  Write-Host 'ERROR: router returned no model IDs.' -ForegroundColor Red;" ^
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
REM ROUTE ALL CLAUDE CODE MODEL ROLES TO THE SELECTED LOCAL MODEL
REM ============================================================================

set "ANTHROPIC_MODEL=%CLAUDE_DGX_MODEL%"
set "ANTHROPIC_DEFAULT_FABLE_MODEL=%CLAUDE_DGX_MODEL%"
set "ANTHROPIC_DEFAULT_OPUS_MODEL=%CLAUDE_DGX_MODEL%"
set "ANTHROPIC_DEFAULT_SONNET_MODEL=%CLAUDE_DGX_MODEL%"
set "ANTHROPIC_DEFAULT_HAIKU_MODEL=%CLAUDE_DGX_MODEL%"

set "CLAUDE_CODE_SUBAGENT_MODEL=%CLAUDE_DGX_MODEL%"

set "ANTHROPIC_CUSTOM_MODEL_OPTION=%CLAUDE_DGX_MODEL%"
set "ANTHROPIC_CUSTOM_MODEL_OPTION_NAME=GPU Cluster - %CLAUDE_DGX_MODEL%"


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
echo   Router:         %ANTHROPIC_BASE_URL%  (5090 -^> 3090 -^> Spark)
echo   Routing:        dynamic priority, 5090 first
echo   Total context:  %CLAUDE_CODE_MAX_CONTEXT_TOKENS% tokens
echo   Compact window: %CLAUDE_CODE_AUTO_COMPACT_WINDOW% tokens
echo   Max response:   %CLAUDE_CODE_MAX_OUTPUT_TOKENS% tokens
echo   Thinking:       OFF
echo   MCP tool cap:   %MAX_MCP_OUTPUT_TOKENS% tokens
echo   Router key:     configured
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
  %*

set "EXIT_CODE=%ERRORLEVEL%"

echo.
echo Claude Code exited with code %EXIT_CODE%.
echo.

endlocal & exit /b %EXIT_CODE%
