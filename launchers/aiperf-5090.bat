@echo off
setlocal EnableExtensions

REM ============================================================================
REM
REM
REM
REM ============================================================================

set "REPO_ROOT=%~dp0.."
set "TOOL_DIR=%REPO_ROOT%\tools\aiperf"
set "VENV_PY=%TOOL_DIR%\.venv\Scripts\python.exe"
set "AIPERF_EXE=%TOOL_DIR%\.venv\Scripts\aiperf.exe"
set "CONFIG=%TOOL_DIR%\5090-benchmark.yaml"

if not exist "%VENV_PY%" (
    echo.
    echo ERROR: AIPerf venv not found at:
    echo   %VENV_PY%
    echo.
    echo Run: python -m venv %TOOL_DIR%\.venv ^&^& %TOOL_DIR%\.venv\Scripts\pip install aiperf
    exit /b 1
)

if not exist "%CONFIG%" (
    echo.
    echo ERROR: config file not found: %CONFIG%
    exit /b 2
)

for /f "delims=" %%s in ('powershell -NoLogo -NoProfile -Command "Get-Date -Format 'yyyyMMdd-HHmmss'"') do (
    set "STAMP=%%s"
)
if not defined STAMP (
    set "STAMP=manual"
)
set "RESULTS_DIR=%TOOL_DIR%\results\5090-%STAMP%"
if not exist "%RESULTS_DIR%" mkdir "%RESULTS_DIR%"
set "AIPERF_RESULTS_DIR=%RESULTS_DIR%"

echo.
echo =============================================================================
echo NVIDIA AIPerf - RTX 5090 benchmark launcher
echo   Target      : http://192.168.86.37:8201  (vLLM, model qwen3.8)
echo   Config      : %CONFIG%
echo   Results dir : %RESULTS_DIR%
echo   venv        : %TOOL_DIR%\.venv
echo   AIPerf      : %AIPERF_EXE%
echo =============================================================================
echo.

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command ^
  "$url = 'http://192.168.86.37:8201';" ^
  "try {" ^
  "  $r = Invoke-RestMethod -Uri ($url + '/health') -Method Get -TimeoutSec 15;" ^
  "  Write-Host ('vLLM healthy: ' + $r.healthy + '/' + $r.total + ' endpoints');" ^
  "} catch {" ^
  "  Write-Host ('WARNING: vLLM /health unreachable: ' + $url) -ForegroundColor Yellow;" ^
  "  Write-Host ('       ' + $_.Exception.Message) -ForegroundColor DarkYellow;" ^
  "}"

REM ---- fix the SSL cert-chain error (Windows TLS root-store quirk) ----
REM The builtin tokenizer downloads tiktoken from openaipublic.blob.core.windows.net;
REM Windows TLS fails to verify the cert chain ("Basic Constraints of CA cert
REM not marked critical"). AIPerf's HTTP client honors AIPERF_HTTP_SSL_VERIFY;
REM setting it to false skips cert verification so the download succeeds.
set "AIPERF_HTTP_SSL_VERIFY=false"

echo.
echo Starting AIPerf (dashboard UI + 5090 profile)...
echo.
"%AIPERF_EXE%" profile --config "%CONFIG%" %*

set "EXIT_CODE=%ERRORLEVEL%"
echo.
echo AIPerf exited with code %EXIT_CODE%.
echo Results: %RESULTS_DIR%
echo.
endlocal & exit /b %EXIT_CODE%
