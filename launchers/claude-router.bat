@echo off
setlocal EnableExtensions

REM ============================================================================
REM Load .env (real values: ROUTER_API_KEY, HOST_* IPs). If the user's shell
REM already exported these, we keep those; otherwise pull them from ..\.env.
REM ============================================================================
set "REPO_ENV=%~dp0..\.env"
if not defined ROUTER_API_KEY (
    for /f "tokens=1,* delims==" %%A in ('findstr /B "ROUTER_API_KEY=" "%REPO_ENV%" 2^>nul') do set "ROUTER_API_KEY=%%B"
)
if not defined ROUTER_HOST (
    for /f "tokens=1,* delims==" %%A in ('findstr /B "HOST_DATABRICK=" "%REPO_ENV%" 2^>nul') do set "ROUTER_HOST=%%B"
)
if not defined ROUTER_HOST set "ROUTER_HOST=192.168.86.48"
if not defined ROUTER_PORT set "ROUTER_PORT=8001"

REM ============================================================================
REM Claude Code -> DETERMINISTIC Go LLM ROUTER (handoff build)
REM
REM   Router  : Databrick 192.168.86.48:8001  (llm-router, local image 1.0.0)
REM   Backend : RedPCv2 RTX 5090 vLLM  192.168.86.37:8201  (single seed)
REM   Alias   : local-coding  ->  qwen3.8  (router translates; do not set qwen3.8)
REM   Strategy: deterministic priority, static atomic capacity = 1
REM   Context : full 262,144  /  thinking OFF
REM
REM Rollback (bypass the router, talk to the 5090 directly):
REM   claude-direct5090.bat
REM ============================================================================

REM ---- new router (Databrick, endpoint 3, port 8001) ----
REM ROUTER_URL / ROUTER_API_KEY come from ..\.env (or the current environment).
set "ROUTER_URL=http://%ROUTER_HOST%:%ROUTER_PORT%"
set "ANTHROPIC_BASE_URL=%ROUTER_URL%"

REM The router advertises /v1/models with alias "local-coding" + backend "qwen3.8".
REM Point Claude Code at the public alias; the router rewrites it to qwen3.8.
if not defined ROUTER_API_KEY (
    echo ERROR: ROUTER_API_KEY not set. Source ..\.env or export it in your shell.
    exit /b 7
)
set "ANTHROPIC_AUTH_TOKEN=%ROUTER_API_KEY%"
set "ANTHROPIC_MODEL=local-coding"

REM ============================================================================
REM FULL 262K CONTEXT (single 5090 stream runs the full 262,144)
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

REM Keep compaction ENABLED.
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
REM ROUTE ALL CLAUDE CODE MODEL ROLES TO THE ALIAS
REM ============================================================================
set "ANTHROPIC_DEFAULT_FABLE_MODEL=local-coding"
set "ANTHROPIC_DEFAULT_OPUS_MODEL=local-coding"
set "ANTHROPIC_DEFAULT_SONNET_MODEL=local-coding"
set "ANTHROPIC_DEFAULT_HAIKU_MODEL=local-coding"
set "CLAUDE_CODE_SUBAGENT_MODEL=local-coding"
set "ANTHROPIC_CUSTOM_MODEL_OPTION=local-coding"
set "ANTHROPIC_CUSTOM_MODEL_OPTION_NAME=Router - local-coding"

REM ============================================================================
REM VERIFY THE ROUTER IS UP
REM ============================================================================
echo.
echo =============================================================================
echo DETERMINISTIC ROUTER MODE  (router: 5090 only, static cap 1)
echo =============================================================================
echo   Router      : %ANTHROPIC_BASE_URL%
echo   Model alias : %ANTHROPIC_MODEL%  (backend: qwen3.8)
echo   Context     : %CLAUDE_DGX_CONTEXT%
echo   Compact at  : %CLAUDE_CODE_AUTO_COMPACT_WINDOW%
echo   Max response: %CLAUDE_CODE_MAX_OUTPUT_TOKENS%
echo   Thinking    : OFF
echo   Rollback    : claude-direct5090.bat
echo =============================================================================
echo.

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command ^
  "$url = $env:ANTHROPIC_BASE_URL.TrimEnd('/');" ^
  "try {" ^
  "  $health = Invoke-RestMethod -Uri ($url + '/health') -Method Get -TimeoutSec 15;" ^
  "  Write-Host ('Router healthy: ' + $health.healthy + '/' + $health.total + ' endpoints');"; ^
  "} catch {" ^
  "  Write-Host ('ERROR: router unreachable: ' + $url) -ForegroundColor Red;" ^
  "  Write-Host ('       ' + $_.Exception.Message) -ForegroundColor Yellow;" ^
  "  exit 2;" ^
  "}"

set "ROUTER_EXIT=%ERRORLEVEL%"
if not "%ROUTER_EXIT%"=="0" (
    echo.
    echo Claude Code was not started.
    exit /b %ROUTER_EXIT%
)

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
REM DISPLAY + START
REM ============================================================================
echo.
echo Starting Claude Code
echo =============================================================================
echo   Model:          %ANTHROPIC_MODEL%  (backend qwen3.8)
echo   Endpoint:       %ANTHROPIC_BASE_URL%/v1/messages
echo   Router:         %ANTHROPIC_BASE_URL%  (deterministic 5090, cap 1)
echo   Total context:  %CLAUDE_CODE_MAX_CONTEXT_TOKENS% tokens
echo   Compact window: %CLAUDE_CODE_AUTO_COMPACT_WINDOW% tokens
echo   Max response:   %CLAUDE_CODE_MAX_OUTPUT_TOKENS% tokens
echo   Thinking:       OFF
echo   CLI:            %REAL_CLAUDE%
echo =============================================================================
echo.
echo WARNING: Claude Code can modify, delete, and execute files without approval.
echo.

call "%REAL_CLAUDE%" ^
  --model "%ANTHROPIC_MODEL%" ^
  --dangerously-skip-permissions ^
  %*

set "EXIT_CODE=%ERRORLEVEL%"
echo.
echo Claude Code exited with code %EXIT_CODE%.
echo.

endlocal & exit /b %EXIT_CODE%
