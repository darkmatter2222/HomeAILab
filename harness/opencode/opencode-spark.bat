@echo off
setlocal EnableExtensions
REM Load lab host IPs + router key from .env (harness\.env or the repo root .env).
call "%~dp0..\load-env.bat"

REM ============================================================================
REM OpenCode -> DIRECT DGX SPARK (GB10 / Blackwell) - Flash-Next 180B MoE
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
REM   Caveat       : ~60-120 s cold TTFT (SSD-PLE prefill)
REM
REM This launcher builds an isolated temporary OpenCode config so it does NOT
REM overwrite your normal global/project OpenCode configuration.
REM ============================================================================

REM ---- direct DGX Spark Flash-Next endpoint ----
REM Probe selects the first reachable endpoint.
set "QWEN_SPARK_URL="
set "OPENCODE_BASE_URL="
set "OPENCODE_PROVIDER=dgx-spark"

REM ============================================================================
REM FULL 262K CONTEXT
REM ============================================================================
REM Total model context : 262,144
REM Compact reserve     : 16,384
REM Effective threshold : 245,760
REM Max response        : 8,192
REM ============================================================================

set "OPENCODE_DGX_CONTEXT=262144"
set "OPENCODE_COMPACT_RESERVE=16384"
set "OPENCODE_COMPACT_AT=245760"
set "OPENCODE_MAX_OUTPUT_TOKENS=8192"

REM OpenCode's current experimental output cap keeps generation aligned with
REM the model definition below. If OpenCode later removes this variable, the
REM model limit in OPENCODE_CONFIG still advertises the correct 8,192 limit.
set "OPENCODE_EXPERIMENTAL_OUTPUT_TOKEN_MAX=8192"

REM Thinking is OFF in the ds4 server chat template (enable_thinking=false).
REM The generated OpenCode model metadata also declares reasoning=false.

REM ============================================================================
REM LONG-RUN / SLOW-LOCAL-MODEL TIMEOUTS
REM ============================================================================
REM OpenCode provider timeout: 60 hours/request.
REM OpenCode streamed-chunk timeout: 20 hours.
REM Header timeout is disabled because Spark can spend a long time in prefill.
REM Bash default timeout: 100 minutes.
REM ============================================================================

set "OPENCODE_REQUEST_TIMEOUT_MS=216000000"
set "OPENCODE_CHUNK_TIMEOUT_MS=72000000"
set "OPENCODE_EXPERIMENTAL_BASH_DEFAULT_TIMEOUT_MS=6000000"

REM Temporary runtime files.
set "MODEL_FILE=%TEMP%\opencode-spark-model-%RANDOM%-%RANDOM%.tmp"
set "ENDPOINT_FILE=%TEMP%\opencode-spark-endpoint-%RANDOM%-%RANDOM%.tmp"
set "OPENCODE_CONFIG=%TEMP%\opencode-spark-config-%RANDOM%-%RANDOM%.json"

REM ============================================================================
REM AUTO-DETECT DIRECT DGX SPARK ENDPOINT
REM ============================================================================
REM   1) ${HOST_DGXSPARK}:8401  DGX Spark published port
REM   2) 127.0.0.1:8401      localhost fallback
REM ============================================================================

echo.
echo =============================================================================
echo DIRECT DGX SPARK MODE  ^(OpenCode, direct backend, no router^)
echo =============================================================================
echo   GPU          : DGX Spark GB10
echo   Model        : Qwen3.8-Flash-Next 180B MoE ^(native vision^)
echo   Host         : %HOST_DGXSPARK%
echo   Port         : 8401
echo   Context      : %OPENCODE_DGX_CONTEXT%
echo   Compact at   : %OPENCODE_COMPACT_AT%
echo   Max response : %OPENCODE_MAX_OUTPUT_TOKENS%
echo   Thinking     : OFF
echo   Cold start   : ~60-120 s TTFT ^(SSD-PLE prefill^)
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
    if exist "%OPENCODE_CONFIG%" del /q "%OPENCODE_CONFIG%" >nul 2>&1
    echo.
    echo Run this command to inspect Docker port publication:
    echo   docker ps --format "table {{.Names}}\t{{.Ports}}"
    echo.
    echo OpenCode was not started.
    exit /b %ENDPOINT_EXIT%
)

set /p "QWEN_SPARK_URL="<"%ENDPOINT_FILE%"
del /q "%ENDPOINT_FILE%" >nul 2>&1
set "OPENCODE_BASE_URL=%QWEN_SPARK_URL%/v1"

echo.
echo Selected backend: %QWEN_SPARK_URL%
echo.
echo Probing:
echo   %QWEN_SPARK_URL%/health
echo   %OPENCODE_BASE_URL%/models
echo.

REM ============================================================================
REM DISCOVER MODEL ID
REM ============================================================================

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference = 'Stop';" ^
  "$root = $env:QWEN_SPARK_URL.TrimEnd('/');" ^
  "try {" ^
  "  $null = Invoke-RestMethod -Uri ($root + '/health') -Method Get -TimeoutSec 1200;" ^
  "} catch {" ^
  "  Write-Host '';" ^
  "  Write-Host ('ERROR: DGX Spark Flash-Next became unreachable: ' + $root) -ForegroundColor Red;" ^
  "  Write-Host ('       ' + $_.Exception.Message) -ForegroundColor Yellow;" ^
  "  exit 2;" ^
  "};" ^
  "Write-Host 'DGX Spark Flash-Next health: OK';" ^
  "try {" ^
  "  $response = Invoke-RestMethod -Uri ($root + '/v1/models') -Method Get -TimeoutSec 1200;" ^
  "} catch {" ^
  "  Write-Host '';" ^
  "  Write-Host ('ERROR: DGX Spark /v1/models unreachable: ' + $root) -ForegroundColor Red;" ^
  "  Write-Host ('       ' + $_.Exception.Message) -ForegroundColor Yellow;" ^
  "  exit 2;" ^
  "};" ^
  "$models = @($response.data | Where-Object { $null -ne $_.id -and ([string]$_.id).Trim() } | ForEach-Object { ([string]$_.id).Trim() });" ^
  "if ($models.Count -eq 0) {" ^
  "  Write-Host 'ERROR: Backend returned no model IDs.' -ForegroundColor Red;" ^
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
    if exist "%OPENCODE_CONFIG%" del /q "%OPENCODE_CONFIG%" >nul 2>&1
    echo.
    echo OpenCode was not started.
    exit /b %DISCOVERY_EXIT%
)

if not exist "%MODEL_FILE%" (
    echo.
    echo ERROR: Model discovery did not return a model.
    if exist "%OPENCODE_CONFIG%" del /q "%OPENCODE_CONFIG%" >nul 2>&1
    exit /b 4
)

set /p "OPENCODE_DGX_MODEL="<"%MODEL_FILE%"
del /q "%MODEL_FILE%" >nul 2>&1

if not defined OPENCODE_DGX_MODEL (
    echo.
    echo ERROR: Selected model ID was empty.
    if exist "%OPENCODE_CONFIG%" del /q "%OPENCODE_CONFIG%" >nul 2>&1
    exit /b 5
)

set "OPENCODE_MODEL=%OPENCODE_PROVIDER%/%OPENCODE_DGX_MODEL%"

REM ============================================================================
REM BUILD ISOLATED OPENCODE CONFIG
REM ============================================================================
REM OpenCode expects custom OpenAI-compatible providers to use
REM @ai-sdk/openai-compatible with a baseURL ending in /v1.
REM
REM Important metadata:
REM   - context/output limits are explicit
REM   - tool_call=true keeps coding tools available
REM   - reasoning=false matches ds4 thinking-off mode
REM   - modalities explicitly enable text + image input
REM   - small_model is pinned to the same local model (no cloud fallback)
REM   - compaction reserve 16,384 -> effective 245,760-token threshold
REM   - permission "*"=allow plus --auto -> unrestricted local agent
REM ============================================================================

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference = 'Stop';" ^
  "$model = $env:OPENCODE_DGX_MODEL;" ^
  "$providerId = $env:OPENCODE_PROVIDER;" ^
  "$fullModel = $env:OPENCODE_MODEL;" ^
  "$models = [ordered]@{};" ^
  "$models[$model] = [ordered]@{" ^
  "  name = ('DGX Spark Flash-Next Direct - ' + $model);" ^
  "  reasoning = $false;" ^
  "  tool_call = $true;" ^
  "  modalities = [ordered]@{ input = @('text','image'); output = @('text') };" ^
  "  limit = [ordered]@{ context = 262144; output = 8192 }" ^
  "};" ^
  "$providers = [ordered]@{};" ^
  "$providers[$providerId] = [ordered]@{" ^
  "  npm = '@ai-sdk/openai-compatible';" ^
  "  name = 'DGX Spark Flash-Next Direct';" ^
  "  options = [ordered]@{" ^
  "    baseURL = $env:OPENCODE_BASE_URL;" ^
  "    timeout = [int64]$env:OPENCODE_REQUEST_TIMEOUT_MS;" ^
  "    chunkTimeout = [int64]$env:OPENCODE_CHUNK_TIMEOUT_MS;" ^
  "    headerTimeout = $false" ^
  "  };" ^
  "  models = $models" ^
  "};" ^
  "$permission = [ordered]@{};" ^
  "$permission['*'] = 'allow';" ^
  "$config = [ordered]@{" ^
  "  '$schema' = 'https://opencode.ai/config.json';" ^
  "  model = $fullModel;" ^
  "  small_model = $fullModel;" ^
  "  compaction = [ordered]@{ auto = $true; prune = $false; reserved = 16384 };" ^
  "  permission = $permission;" ^
  "  provider = $providers" ^
  "};" ^
  "$json = $config | ConvertTo-Json -Depth 12;" ^
  "[System.IO.File]::WriteAllText($env:OPENCODE_CONFIG, $json, [System.Text.UTF8Encoding]::new($false));"

set "CONFIG_EXIT=%ERRORLEVEL%"
if not "%CONFIG_EXIT%"=="0" (
    echo.
    echo ERROR: Failed to generate temporary OpenCode configuration.
    if exist "%OPENCODE_CONFIG%" del /q "%OPENCODE_CONFIG%" >nul 2>&1
    exit /b %CONFIG_EXIT%
)

REM ============================================================================
REM LOCATE OPENCODE
REM ============================================================================

set "REAL_OPENCODE="

for /f "delims=" %%I in ('where.exe opencode.exe 2^>nul') do (
    if /I not "%%~fI"=="%~f0" (
        set "REAL_OPENCODE=%%~fI"
        goto :found_opencode
    )
)

for /f "delims=" %%I in ('where.exe opencode.cmd 2^>nul') do (
    if /I not "%%~fI"=="%~f0" (
        set "REAL_OPENCODE=%%~fI"
        goto :found_opencode
    )
)

for /f "delims=" %%I in ('where.exe opencode 2^>nul') do (
    if /I not "%%~fI"=="%~f0" (
        set "REAL_OPENCODE=%%~fI"
        goto :found_opencode
    )
)

if exist "%APPDATA%\npm\opencode.cmd" (
    set "REAL_OPENCODE=%APPDATA%\npm\opencode.cmd"
    goto :found_opencode
)

if exist "%USERPROFILE%\.opencode\bin\opencode.exe" (
    set "REAL_OPENCODE=%USERPROFILE%\.opencode\bin\opencode.exe"
    goto :found_opencode
)

if exist "%USERPROFILE%\.local\bin\opencode.exe" (
    set "REAL_OPENCODE=%USERPROFILE%\.local\bin\opencode.exe"
    goto :found_opencode
)

:found_opencode

if not defined REAL_OPENCODE (
    echo.
    echo ERROR: OpenCode was not found in PATH or common install locations.
    echo.
    echo Try: where opencode
    echo.
    if exist "%OPENCODE_CONFIG%" del /q "%OPENCODE_CONFIG%" >nul 2>&1
    exit /b 6
)

REM ============================================================================
REM DISPLAY FINAL CONFIGURATION
REM ============================================================================

echo.
echo Starting OpenCode
echo =============================================================================
echo   Model:          %OPENCODE_MODEL%
echo   Upstream ID:    %OPENCODE_DGX_MODEL%
echo   Endpoint:       %OPENCODE_BASE_URL%/chat/completions
echo   Backend:        DGX SPARK FLASH-NEXT DIRECT - NO ROUTER
echo   Direct URL:     %QWEN_SPARK_URL%
echo   Total context:  %OPENCODE_DGX_CONTEXT% tokens
echo   Compact window: %OPENCODE_COMPACT_AT% tokens ^(16,384 reserve^)
echo   Max response:   %OPENCODE_MAX_OUTPUT_TOKENS% tokens
echo   Thinking:       OFF ^(ds4 enforced^)
echo   Image input:    NATIVE VISION ^(text + image declared^)
echo   API timeout:    60 hours/request
echo   Header timeout: OFF ^(slow Spark prefill allowed^)
echo   Stream idle:    20 hours between chunks
echo   Bash timeout:   100 minutes default
echo   Permissions:    AUTO / unrestricted unless explicitly denied elsewhere
echo   Config:         %OPENCODE_CONFIG%
echo   CLI:            %REAL_OPENCODE%
echo =============================================================================
echo.
echo EXPECTED CONTEXT:
echo   OpenCode should report a 262,144-token model context.
echo   Automatic compaction should reserve 16,384 tokens, yielding an effective
echo   threshold of approximately 245,760 tokens.
echo   NOTE: cold-start TTFT is ~60-120 s ^(SSD-PLE prefill^); the first response
echo   will be slow until the page cache is warm.
echo.
echo WARNING: OpenCode can modify, delete, and execute files without approval.
echo.

REM ============================================================================
REM START OPENCODE
REM ============================================================================
REM --model uses OpenCode's required provider/model form.
REM --auto automatically approves permission requests that are not denied.
REM Any arguments passed to this launcher are forwarded to OpenCode.

call "%REAL_OPENCODE%" ^
  --model "%OPENCODE_MODEL%" ^
  --auto ^
  %*

set "EXIT_CODE=%ERRORLEVEL%"

REM Clean up the temporary config after this OpenCode process exits.
if exist "%OPENCODE_CONFIG%" del /q "%OPENCODE_CONFIG%" >nul 2>&1

echo.
echo OpenCode exited with code %EXIT_CODE%.
echo.

endlocal & exit /b %EXIT_CODE%
