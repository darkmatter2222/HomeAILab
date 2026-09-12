@echo off
setlocal EnableExtensions
REM Load lab host IPs + router key from .env (harness\.env or the repo root .env).
call "%~dp0..\load-env.bat"

REM ============================================================================
REM OpenCode -> DIRECT RTX 3090 llama.cpp (Databrick)
REM DIRECT BACKEND (router bypass)
REM
REM FULL 262,144-TOKEN CONTEXT / THINKING OFF / IMAGE INPUT BLOCKED
REM
REM Direct backend:
REM   Databrick RTX 3090 (llama.cpp server-cuda12)
REM   Host/port   : auto-detected
REM   Preferred    : ${HOST_3090}, llama.cpp contract ports 8100-8199
REM   Fallback     : ${HOST_3090}:8006 + localhost equivalents
REM   Engine       : llama.cpp server-cuda12
REM   Model alias  : discovered dynamically from /v1/models
REM
REM llama.cpp exposes an OpenAI-compatible API at /v1/chat/completions and
REM /v1/models. It has no /health endpoint, so readiness is checked by TCP.
REM
REM This launcher builds an isolated temporary OpenCode config. It does NOT
REM overwrite your normal global OpenCode configuration.
REM ============================================================================

REM ---- direct RTX 3090 llama.cpp endpoint ----
set "QWEN_3090_URL="
set "OPENCODE_BASE_URL="
set "OPENCODE_PROVIDER=rtx-3090"

REM ============================================================================
REM FULL 262K CONTEXT
REM ============================================================================
REM Total model context : 262,144
REM Compact reserve     : 16,384
REM Effective threshold : 245,760
REM Max response        : 8,192
REM ============================================================================

set "OPENCODE_3090_CONTEXT=262144"
set "OPENCODE_COMPACT_RESERVE=16384"
set "OPENCODE_COMPACT_AT=245760"
set "OPENCODE_MAX_OUTPUT_TOKENS=8192"

REM OpenCode experimental global output cap. The model definition below also
REM explicitly declares the 8,192-token output limit.
set "OPENCODE_EXPERIMENTAL_OUTPUT_TOKEN_MAX=8192"

REM Thinking OFF. The model metadata below advertises reasoning=false; your
REM llama.cpp chat-template/server contract should continue to force thinking off.

REM ============================================================================
REM LONG-RUN / LOCAL-MODEL TIMEOUTS
REM ============================================================================
REM Preserve the original 3090 launcher behavior:
REM   Request timeout : 6 hours
REM   Stream timeout  : 2 hours between streamed chunks
REM   Bash timeout    : 10 minutes default
REM ============================================================================

set "OPENCODE_REQUEST_TIMEOUT_MS=21600000"
set "OPENCODE_CHUNK_TIMEOUT_MS=7200000"
set "OPENCODE_EXPERIMENTAL_BASH_DEFAULT_TIMEOUT_MS=600000"

REM Temporary runtime files.
set "MODEL_FILE=%TEMP%\opencode-3090-model-%RANDOM%-%RANDOM%.tmp"
set "ENDPOINT_FILE=%TEMP%\opencode-3090-endpoint-%RANDOM%-%RANDOM%.tmp"
set "OPENCODE_CONFIG=%TEMP%\opencode-3090-config-%RANDOM%-%RANDOM%.json"

REM ============================================================================
REM AUTO-DETECT DIRECT RTX 3090 ENDPOINT
REM ============================================================================
REM Do NOT hard-code one published port.
REM
REM Discovery order:
REM   1) Databrick host ${HOST_3090}
REM   2) localhost fallback
REM
REM Port order:
REM   1) 8101  (original launcher / preferred contract slot)
REM   2) 8006  (current compose publishes 8006:8006)
REM   3) remaining 8100-8199 llama.cpp contract range
REM   4) remaining 8001-8099 legacy/fallback range
REM
REM Discovery is two-stage:
REM   - fast ~150 ms TCP probe
REM   - only if TCP is open, validate OpenAI compatibility via /v1/models
REM
REM A port is accepted only if /v1/models returns at least one model ID.
REM ============================================================================

echo.
echo =============================================================================
echo DIRECT RTX 3090 MODE  ^(OpenCode, direct backend, no router^)
echo =============================================================================
echo   GPU          : RTX 3090
echo   Runtime      : llama.cpp server-cuda12
echo   Endpoint     : AUTO-DETECT
echo   Remote host  : %HOST_3090%
echo   Port search  : 8101, 8006, then 8100-8199 / 8001-8099
echo   Context      : %OPENCODE_3090_CONTEXT%
echo   Compact at   : %OPENCODE_COMPACT_AT%
echo   Max response : %OPENCODE_MAX_OUTPUT_TOKENS%
echo   Thinking     : OFF
echo   Image input  : BLOCKED
echo =============================================================================
echo.
echo Searching for reachable RTX 3090 llama.cpp endpoint...
echo.

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference = 'SilentlyContinue';" ^
  "$hosts = @($env:HOST_3090,'127.0.0.1');" ^
  "$ports = @(" ^
  "  8101," ^
  "  8006" ^
  ");" ^
  "$ports += @(8100..8199 | Where-Object { $_ -ne 8101 });" ^
  "$ports += @(8001..8099 | Where-Object { $_ -ne 8006 });" ^
  "$ports = @($ports | Select-Object -Unique);" ^
  "$selected = $null;" ^
  "$selectedModels = @();" ^
  "foreach ($h in $hosts) {" ^
  "  Write-Host ('Scanning host ' + $h + ' ...') -ForegroundColor Cyan;" ^
  "  foreach ($p in $ports) {" ^
  "    $tcp = $null;" ^
  "    $open = $false;" ^
  "    try {" ^
  "      $tcp = New-Object System.Net.Sockets.TcpClient;" ^
  "      $iar = $tcp.BeginConnect($h, $p, $null, $null);" ^
  "      if ($iar.AsyncWaitHandle.WaitOne(150, $false)) {" ^
  "        $tcp.EndConnect($iar);" ^
  "        $open = $true;" ^
  "      }" ^
  "    } catch {" ^
  "      $open = $false;" ^
  "    } finally {" ^
  "      if ($null -ne $tcp) { $tcp.Close(); }" ^
  "    }" ^
  "    if (-not $open) { continue; }" ^
  "    $url = 'http://' + $h + ':' + $p;" ^
  "    Write-Host ('  open port ' + $p + ' -> validating /v1/models ...') -NoNewline;" ^
  "    try {" ^
  "      $response = Invoke-RestMethod -Uri ($url + '/v1/models') -Method Get -TimeoutSec 3;" ^
  "      $models = @($response.data | Where-Object { $null -ne $_.id -and ([string]$_.id).Trim() } | ForEach-Object { ([string]$_.id).Trim() });" ^
  "      if ($models.Count -gt 0) {" ^
  "        Write-Host (' MATCH [' + ($models -join ', ') + ']') -ForegroundColor Green;" ^
  "        $selected = $url;" ^
  "        $selectedModels = $models;" ^
  "        break;" ^
  "      } else {" ^
  "        Write-Host ' not llama.cpp/OpenAI model endpoint' -ForegroundColor DarkGray;" ^
  "      }" ^
  "    } catch {" ^
  "      Write-Host ' not compatible' -ForegroundColor DarkGray;" ^
  "    }" ^
  "  }" ^
  "  if ($selected) { break; }" ^
  "};" ^
  "if (-not $selected) {" ^
  "  Write-Host '';" ^
  "  Write-Host 'ERROR: No reachable RTX 3090 llama.cpp OpenAI endpoint was found.' -ForegroundColor Red;" ^
  "  Write-Host ('Checked ' + $env:HOST_3090 + ' and localhost across ports 8001-8199.') -ForegroundColor Yellow;" ^
  "  exit 2;" ^
  "};" ^
  "Write-Host '';" ^
  "Write-Host ('Auto-detected backend: ' + $selected) -ForegroundColor Green;" ^
  "Write-Host ('Advertised model(s): ' + ($selectedModels -join ', ')) -ForegroundColor Green;" ^
  "[System.IO.File]::WriteAllText($env:ENDPOINT_FILE, $selected);"

set "ENDPOINT_EXIT=%ERRORLEVEL%"
if not "%ENDPOINT_EXIT%"=="0" (
    if exist "%ENDPOINT_FILE%" del /q "%ENDPOINT_FILE%" >nul 2>&1
    if exist "%OPENCODE_CONFIG%" del /q "%OPENCODE_CONFIG%" >nul 2>&1
    echo.
    echo Run this command on Databrick to inspect the 3090 stack publication:
    echo   ssh databricks 'docker ps --format "table {{.Names}}\t{{.Ports}}"'
    echo.
    echo OpenCode was not started.
    exit /b %ENDPOINT_EXIT%
)

set /p "QWEN_3090_URL="<"%ENDPOINT_FILE%"
del /q "%ENDPOINT_FILE%" >nul 2>&1
set "OPENCODE_BASE_URL=%QWEN_3090_URL%/v1"

echo.
echo Auto-detected backend: %QWEN_3090_URL%
echo.
echo Probing:
echo   %OPENCODE_BASE_URL%/models
echo.

REM ============================================================================
REM DISCOVER MODEL ID
REM ============================================================================

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference = 'Stop';" ^
  "$url = $env:QWEN_3090_URL.TrimEnd('/');" ^
  "try {" ^
  "  $response = Invoke-RestMethod -Uri ($url + '/v1/models') -Method Get -TimeoutSec 60;" ^
  "} catch {" ^
  "  Write-Host '';" ^
  "  Write-Host ('ERROR: RTX 3090 llama.cpp /v1/models unreachable: ' + $url) -ForegroundColor Red;" ^
  "  Write-Host ('       ' + $_.Exception.Message) -ForegroundColor Yellow;" ^
  "  exit 2;" ^
  "};" ^
  "Write-Host 'RTX 3090 llama.cpp: reachable';" ^
  "$models = @($response.data | Where-Object { $null -ne $_.id -and ([string]$_.id).Trim() } | ForEach-Object { ([string]$_.id).Trim() });" ^
  "if ($models.Count -eq 0) {" ^
  "  Write-Host 'ERROR: llama.cpp returned no model IDs.' -ForegroundColor Red;" ^
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

set /p "OPENCODE_3090_MODEL="<"%MODEL_FILE%"
del /q "%MODEL_FILE%" >nul 2>&1

if not defined OPENCODE_3090_MODEL (
    echo.
    echo ERROR: Selected model ID was empty.
    if exist "%OPENCODE_CONFIG%" del /q "%OPENCODE_CONFIG%" >nul 2>&1
    exit /b 5
)

set "OPENCODE_MODEL=%OPENCODE_PROVIDER%/%OPENCODE_3090_MODEL%"

REM ============================================================================
REM BUILD ISOLATED OPENCODE CONFIG
REM ============================================================================
REM OpenCode's V1/stable config uses @ai-sdk/openai-compatible for llama.cpp's
REM /v1/chat/completions API and expects baseURL to end in /v1.
REM
REM Important behavior carried over from the Claude Code launcher:
REM   - explicit 262,144 context and 8,192 output limits
REM   - tool calling enabled
REM   - reasoning/thinking disabled
REM   - TEXT-ONLY modality (no image payloads sent to this 3090 endpoint)
REM   - image file reads explicitly denied by extension
REM   - small_model pinned to this same local endpoint/model
REM   - compaction reserve 16,384 -> effective ~245,760-token threshold
REM   - all other permissions allowed; --auto approves non-denied actions
REM ============================================================================

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference = 'Stop';" ^
  "$model = $env:OPENCODE_3090_MODEL;" ^
  "$providerId = $env:OPENCODE_PROVIDER;" ^
  "$fullModel = $env:OPENCODE_MODEL;" ^
  "$models = [ordered]@{};" ^
  "$models[$model] = [ordered]@{" ^
  "  name = ('RTX 3090 Direct - ' + $model);" ^
  "  reasoning = $false;" ^
  "  tool_call = $true;" ^
  "  modalities = [ordered]@{ input = @('text'); output = @('text') };" ^
  "  limit = [ordered]@{ context = 262144; output = 8192 }" ^
  "};" ^
  "$providers = [ordered]@{};" ^
  "$providers[$providerId] = [ordered]@{" ^
  "  npm = '@ai-sdk/openai-compatible';" ^
  "  name = 'RTX 3090 llama.cpp Direct';" ^
  "  options = [ordered]@{" ^
  "    baseURL = $env:OPENCODE_BASE_URL;" ^
  "    timeout = [int64]$env:OPENCODE_REQUEST_TIMEOUT_MS;" ^
  "    chunkTimeout = [int64]$env:OPENCODE_CHUNK_TIMEOUT_MS" ^
  "  };" ^
  "  models = $models" ^
  "};" ^
  "$readRules = [ordered]@{};" ^
  "$readRules['*'] = 'allow';" ^
  "$readRules['*.png'] = 'deny';" ^
  "$readRules['*.jpg'] = 'deny';" ^
  "$readRules['*.jpeg'] = 'deny';" ^
  "$readRules['*.gif'] = 'deny';" ^
  "$readRules['*.webp'] = 'deny';" ^
  "$readRules['*.bmp'] = 'deny';" ^
  "$readRules['*.tif'] = 'deny';" ^
  "$readRules['*.tiff'] = 'deny';" ^
  "$readRules['*.ico'] = 'deny';" ^
  "$readRules['*.PNG'] = 'deny';" ^
  "$readRules['*.JPG'] = 'deny';" ^
  "$readRules['*.JPEG'] = 'deny';" ^
  "$readRules['*.GIF'] = 'deny';" ^
  "$readRules['*.WEBP'] = 'deny';" ^
  "$readRules['*.BMP'] = 'deny';" ^
  "$readRules['*.TIF'] = 'deny';" ^
  "$readRules['*.TIFF'] = 'deny';" ^
  "$readRules['*.ICO'] = 'deny';" ^
  "$permission = [ordered]@{};" ^
  "$permission['*'] = 'allow';" ^
  "$permission['read'] = $readRules;" ^
  "$config = [ordered]@{" ^
  "  '$schema' = 'https://opencode.ai/config.json';" ^
  "  model = $fullModel;" ^
  "  small_model = $fullModel;" ^
  "  enabled_providers = @($providerId);" ^
  "  compaction = [ordered]@{ auto = $true; prune = $false; reserved = 16384 };" ^
  "  permission = $permission;" ^
  "  provider = $providers" ^
  "};" ^
  "$json = $config | ConvertTo-Json -Depth 12 -Compress;" ^
  "[System.IO.File]::WriteAllText($env:OPENCODE_CONFIG, $json, [System.Text.UTF8Encoding]::new($false));"

set "CONFIG_EXIT=%ERRORLEVEL%"
if not "%CONFIG_EXIT%"=="0" (
    echo.
    echo ERROR: Failed to generate temporary OpenCode configuration.
    if exist "%OPENCODE_CONFIG%" del /q "%OPENCODE_CONFIG%" >nul 2>&1
    exit /b %CONFIG_EXIT%
)

REM Apply the same generated JSON as an inline runtime override. OpenCode loads
REM OPENCODE_CONFIG_CONTENT after project config, preventing a project-local
REM opencode.json from changing this launcher's provider/model/limits/permissions.
set /p "OPENCODE_CONFIG_CONTENT="<"%OPENCODE_CONFIG%"

if not defined OPENCODE_CONFIG_CONTENT (
    echo.
    echo ERROR: Generated OpenCode runtime configuration was empty.
    if exist "%OPENCODE_CONFIG%" del /q "%OPENCODE_CONFIG%" >nul 2>&1
    exit /b 7
)

REM ============================================================================
REM LOCATE OPENCODE
REM ============================================================================

set "REAL_OPENCODE="

REM Skip the OpenCode Deck shim (.opencode-deck\bin): calling it would re-launch
REM opencode in a managed window instead of inside this terminal.
for /f "delims=" %%I in ('where.exe opencode.exe 2^>nul ^| findstr /L /V /C:".opencode-deck\bin"') do (
    if /I not "%%~fI"=="%~f0" (
        set "REAL_OPENCODE=%%~fI"
        goto :found_opencode
    )
)

for /f "delims=" %%I in ('where.exe opencode.cmd 2^>nul ^| findstr /L /V /C:".opencode-deck\bin"') do (
    if /I not "%%~fI"=="%~f0" (
        set "REAL_OPENCODE=%%~fI"
        goto :found_opencode
    )
)

for /f "delims=" %%I in ('where.exe opencode 2^>nul ^| findstr /L /V /C:".opencode-deck\bin"') do (
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
echo   Upstream ID:    %OPENCODE_3090_MODEL%
echo   Endpoint:       %OPENCODE_BASE_URL%/chat/completions
echo   Backend:        RTX 3090 DIRECT - NO ROUTER
echo   Direct URL:     %QWEN_3090_URL%
echo   Runtime:        llama.cpp server-cuda12
echo   Total context:  %OPENCODE_3090_CONTEXT% tokens
echo   Compact window: %OPENCODE_COMPACT_AT% tokens ^(16,384 reserve^)
echo   Max response:   %OPENCODE_MAX_OUTPUT_TOKENS% tokens
echo   Thinking:       OFF
echo   Image input:    BLOCKED ^(text-only model + read denies^)
echo   API timeout:    6 hours/request
echo   Stream idle:    2 hours between chunks
echo   Bash timeout:   10 minutes default
echo   Permissions:    AUTO / unrestricted except image reads
echo   Config file:    %OPENCODE_CONFIG%
echo   Runtime config:  INLINE OVERRIDE ACTIVE
echo   CLI:            %REAL_OPENCODE%
echo =============================================================================
echo.
echo EXPECTED CONTEXT:
echo   OpenCode should report a 262,144-token model context.
echo   Automatic compaction reserves 16,384 tokens, yielding an effective
echo   threshold of approximately 245,760 tokens.
echo.
echo WARNING: OpenCode can modify, delete, and execute files without approval.
echo          Image-file reads are explicitly denied for this text-only backend.
echo.

REM ============================================================================
REM START OPENCODE
REM ============================================================================
REM --model uses OpenCode's provider/model format.
REM --auto automatically approves permissions that are not explicitly denied.
REM Do NOT use --pure here: installed OpenCode plugins/commands (such as /goal)
REM remain available.
REM Any arguments passed to this launcher are forwarded to OpenCode.

call "%REAL_OPENCODE%" ^
  --model "%OPENCODE_MODEL%" ^
  --auto ^
  %*

set "EXIT_CODE=%ERRORLEVEL%"

REM Clean up temporary runtime config after OpenCode exits.
if exist "%OPENCODE_CONFIG%" del /q "%OPENCODE_CONFIG%" >nul 2>&1
if exist "%MODEL_FILE%" del /q "%MODEL_FILE%" >nul 2>&1
if exist "%ENDPOINT_FILE%" del /q "%ENDPOINT_FILE%" >nul 2>&1

echo.
echo OpenCode exited with code %EXIT_CODE%.
echo.

endlocal & exit /b %EXIT_CODE%
