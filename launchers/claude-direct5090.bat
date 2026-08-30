@echo off
setlocal EnableExtensions

REM ============================================================================
REM Load .env (real values: ROUTER_API_KEY, HOST_5090). If the user's shell
REM already exported these, we keep those; otherwise pull them from ..\.env.
REM ============================================================================
set "REPO_ENV=%~dp0..\.env"
if not defined ROUTER_API_KEY (
    for /f "tokens=1,* delims==" %%A in ('findstr /B "ROUTER_API_KEY=" "%REPO_ENV%" 2^>nul') do set "ROUTER_API_KEY=%%B"
)
if not defined HOST_5090 (
    for /f "tokens=1,* delims==" %%A in ('findstr /B "HOST_5090=" "%REPO_ENV%" 2^>nul') do set "HOST_5090=%%B"
)
if not defined HOST_5090 set "HOST_5090=192.168.86.37"
if not defined HOST_5090_PORT set "HOST_5090_PORT=8201"

REM ============================================================================
REM Claude Code -> DIRECT RTX 5090 (ROLLBACK bypass, no router)
REM
REM   Talks straight to the vLLM vLLM endpoint on RedPCv2 (.37:8201).
REM   Use this if the deterministic router on :8001 misbehaves.
REM
REM   Model     : qwen3.8  (the backend's served name; no alias translation)
REM   Context   : full 262,144  /  thinking OFF
REM
REM Normal mode (via router): claude-router.bat
REM ============================================================================

REM QWEN5090_URL / ROUTER_API_KEY come from ..\.env (or the current environment).
set "QWEN5090_URL=http://%HOST_5090%:%HOST_5090_PORT%"
set "ANTHROPIC_BASE_URL=%QWEN5090_URL%"
if not defined ROUTER_API_KEY (
    echo ERROR: ROUTER_API_KEY not set. Source ..\.env or export it in your shell.
    exit /b 7
)
set "ANTHROPIC_AUTH_TOKEN=%ROUTER_API_KEY%"
set "ANTHROPIC_MODEL=qwen3.8"

REM ============================================================================
REM FULL 262K CONTEXT
REM ============================================================================
set "CLAUDE_DGX_CONTEXT=262144"
set "CLAUDE_CODE_MAX_CONTEXT_TOKENS=262144"
set "CLAUDE_CODE_AUTO_COMPACT_WINDOW=245760"
set "CLAUDE_CODE_MAX_OUTPUT_TOKENS=8192"

set "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE="
set "DISABLE_COMPACT="
set "DISABLE_AUTO_COMPACT="
set "CLAUDE_CODE_DISABLE_UNKNOWN_MODEL_WINDOW_ENFORCEMENT="

set "MAX_THINKING_TOKENS=0"
set "CLAUDE_CODE_DISABLE_THINKING=1"
set "MAX_MCP_OUTPUT_TOKENS=8000"

REM ============================================================================
REM ROUTE ALL CLAUDE CODE MODEL ROLES TO THE BACKEND MODEL
REM ============================================================================
set "ANTHROPIC_DEFAULT_FABLE_MODEL=qwen3.8"
set "ANTHROPIC_DEFAULT_OPUS_MODEL=qwen3.8"
set "ANTHROPIC_DEFAULT_SONNET_MODEL=qwen3.8"
set "ANTHROPIC_DEFAULT_HAIKU_MODEL=qwen3.8"
set "CLAUDE_CODE_SUBAGENT_MODEL=qwen3.8"
set "ANTHROPIC_CUSTOM_MODEL_OPTION=qwen3.8"
set "ANTHROPIC_CUSTOM_MODEL_OPTION_NAME=Direct 5090 - qwen3.8"

REM ============================================================================
REM VERIFY THE 5090 IS UP
REM ============================================================================
echo.
echo =============================================================================
echo DIRECT 5090 MODE  (rollback bypass, talks to .37:8201 directly)
echo =============================================================================
echo   Endpoint    : %ANTHROPIC_BASE_URL%
echo   Model       : %ANTHROPIC_MODEL%
echo   Context     : %CLAUDE_DGX_CONTEXT%
echo   Rollback to router: claude-router.bat
echo =============================================================================
echo.

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command ^
  "$url = $env:ANTHROPIC_BASE_URL.TrimEnd('/');" ^
  "try {" ^
  "  $h = Invoke-RestMethod -Uri ($url + '/health') -Method Get -TimeoutSec 15;" ^
  "  Write-Host ('5090 healthy: ' + $h) -ForegroundColor Green;" ^
  "} catch {" ^
  "  Write-Host ('WARNING: 5090 /health probe failed (may still serve): ' + $url) -ForegroundColor Yellow;" ^
  "  Write-Host ('       ' + $_.Exception.Message) -ForegroundColor Yellow;" ^
  "}"

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

echo.
echo Starting Claude Code  (direct 5090, no router)
echo   Model:          %ANTHROPIC_MODEL%
echo   Endpoint:       %ANTHROPIC_BASE_URL%/v1/messages
echo   CLI:            %REAL_CLAUDE%
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
