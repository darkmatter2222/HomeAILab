@echo off
setlocal EnableExtensions
REM Load lab host IPs + router key from .env (harness\.env or the repo root .env).
call "%~dp0..\load-env.bat"

REM ============================================================================
REM GitHub Copilot CLI launcher for a local DGX Spark / vLLM endpoint
REM
REM Behavior:
REM   1. Queries the OpenAI-compatible /models endpoint.
REM   2. If exactly one model is available, selects it automatically.
REM   3. If multiple models are available, presents a numbered selection menu.
REM   4. Locates the real GitHub Copilot CLI on PATH.
REM   5. Starts Copilot in the configured local/autopilot mode.
REM
REM No model names are hard-coded in this launcher.
REM ============================================================================

REM ---- Local OpenAI-compatible endpoint ---------------------------------------
set "COPILOT_PROVIDER_TYPE=openai"
set "COPILOT_PROVIDER_BASE_URL=http://%HOST_3090%:8006/v1"
set "COPILOT_PROVIDER_API_KEY=local-vllm"
set "COPILOT_ALLOW_ALL=true"

REM ---- Temporary file used to return the selected model from PowerShell -------
set "MODEL_FILE=%TEMP%\copilot-dgx-model-%RANDOM%-%RANDOM%.tmp"

echo.
echo Discovering models from:
echo   %COPILOT_PROVIDER_BASE_URL%/models
echo.

REM PowerShell is used only for the HTTP request, JSON parsing, and selection
REM menu. Windows PowerShell is present on standard Windows installations.
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference = 'Stop';" ^
  "$base = $env:COPILOT_PROVIDER_BASE_URL.TrimEnd('/');" ^
  "$headers = @{};" ^
  "if ($env:COPILOT_PROVIDER_API_KEY) { $headers['Authorization'] = 'Bearer ' + $env:COPILOT_PROVIDER_API_KEY };" ^
  "try {" ^
  "  $response = Invoke-RestMethod -Uri ($base + '/models') -Method Get -Headers $headers -TimeoutSec 10;" ^
  "} catch {" ^
  "  Write-Host '';" ^
  "  Write-Host 'ERROR: Could not query the model endpoint.' -ForegroundColor Red;" ^
  "  Write-Host ('       ' + $_.Exception.Message);" ^
  "  exit 2;" ^
  "};" ^
  "$models = @($response.data | ForEach-Object { if ($null -ne $_.id) { ([string]$_.id).Trim() } } | Where-Object { $_ });" ^
  "if ($models.Count -eq 0) {" ^
  "  Write-Host '';" ^
  "  Write-Host 'ERROR: The endpoint returned no usable model IDs.' -ForegroundColor Red;" ^
  "  exit 3;" ^
  "};" ^
  "if ($models.Count -eq 1) {" ^
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
  "    $valid = [int]::TryParse($choice, [ref]$number) -and $number -ge 1 -and $number -le $models.Count;" ^
  "    if (-not $valid) { Write-Host 'Please enter a valid model number.' -ForegroundColor Yellow };" ^
  "  } until ($valid);" ^
  "  $selected = $models[$number - 1];" ^
  "};" ^
  "[System.IO.File]::WriteAllText($env:MODEL_FILE, $selected);" ^
  "exit 0;"

set "DISCOVERY_EXIT=%ERRORLEVEL%"

if not "%DISCOVERY_EXIT%"=="0" (
    if exist "%MODEL_FILE%" del /q "%MODEL_FILE%" >nul 2>&1
    echo.
    echo Copilot was not started.
    exit /b %DISCOVERY_EXIT%
)

if not exist "%MODEL_FILE%" (
    echo.
    echo ERROR: Model discovery completed without returning a selected model.
    exit /b 4
)

set /p "COPILOT_MODEL="<"%MODEL_FILE%"
del /q "%MODEL_FILE%" >nul 2>&1

if not defined COPILOT_MODEL (
    echo.
    echo ERROR: The selected model ID was empty.
    exit /b 5
)

REM ---- Locate the actual GitHub Copilot CLI -----------------------------------
REM Skip this launcher itself if it happens to appear in the results from WHERE.
set "REAL_COPILOT="

for /f "delims=" %%I in ('where.exe copilot 2^>nul') do (
    if /I not "%%~fI"=="%~f0" (
        set "REAL_COPILOT=%%~fI"
        goto :found_copilot
    )
)

:found_copilot
if not defined REAL_COPILOT (
    echo.
    echo ERROR: GitHub Copilot CLI was not found on PATH.
    echo.
    echo Inspect available executables with:
    echo   where copilot
    echo.
    echo Do not name this launcher copilot.bat.
    echo Recommended filename: copilot-dgx.bat
    exit /b 6
)

REM ---- Launch -----------------------------------------------------------------
echo.
echo Starting GitHub Copilot CLI
echo ----------------------------------------------------------------------------
echo   Model:       %COPILOT_MODEL%
echo   Endpoint:    %COPILOT_PROVIDER_BASE_URL%
echo   Provider:    %COPILOT_PROVIDER_TYPE%
echo   CLI:         %REAL_COPILOT%
echo ----------------------------------------------------------------------------
echo.
echo WARNING: Autopilot mode can modify, delete, and execute files.
echo.

call "%REAL_COPILOT%" ^
  --mode=autopilot ^
  --yolo ^
  --no-ask-user ^
  --remote ^
  --stream=on ^
  --context=long_context ^
  --enable-all-github-mcp-tools ^
  --experimental %*

set "EXIT_CODE=%ERRORLEVEL%"
endlocal & exit /b %EXIT_CODE%
