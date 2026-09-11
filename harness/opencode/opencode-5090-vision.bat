@echo off
setlocal EnableExtensions
REM Load lab host IPs + router key from .env (harness\.env or the repo root .env).
call "%~dp0..\load-env.bat"

REM ============================================================================
REM OpenCode -> DIRECT RTX 5090 vLLM
REM DIRECT BACKEND (router bypass)
REM
REM 131,072-TOKEN CONTEXT / THINKING ON / VISION ENABLED
REM
REM Direct backend:
REM   RedPCv2 RTX 5090
REM   LAN IP        : ${HOST_5090}
REM   Published     : 8201
REM   vLLM internal : 8006
REM   Engine        : vLLM 0.28.0
REM   Model alias   : discovered dynamically from /v1/models
REM
REM vLLM exposes an OpenAI-compatible API at /v1/chat/completions,
REM /v1/models, plus /health for readiness.
REM
REM This launcher builds an isolated temporary OpenCode config. It does NOT
REM overwrite your normal global OpenCode configuration.
REM ============================================================================

REM ---- direct RTX 5090 vLLM endpoint ----
set "QWEN_5090_URL="
set "OPENCODE_BASE_URL="
set "OPENCODE_PROVIDER=rtx-5090"

REM ============================================================================
REM HARD ONE-IMAGE PROVIDER GUARD
REM ============================================================================
REM OpenCode retains image attachments from prior Read tool results in session
REM history. Without this guard, a later Read of a second image can cause the
REM provider request to contain BOTH the previous image and the new image.
REM
REM This launcher installs/refreshes a global OpenCode plugin before startup.
REM Immediately before every LLM call the plugin strips all historical image
REM media except the newest image. Textual observations from prior images remain.
REM Result: the provider receives AT MOST ONE IMAGE in every request.
REM
REM Global OpenCode plugin path:
REM   %%USERPROFILE%%\.config\opencode\plugins\one-image-guard.js
REM ============================================================================

set "ONE_IMAGE_GUARD_PATH=%USERPROFILE%\.config\opencode\plugins\one-image-guard.js"
set "OPENCODE_ONE_IMAGE_GUARD_DEBUG=0"

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference = 'Stop';" ^
  "$path = $env:ONE_IMAGE_GUARD_PATH;" ^
  "$dir = [System.IO.Path]::GetDirectoryName($path);" ^
  "[System.IO.Directory]::CreateDirectory($dir) | Out-Null;" ^
  "$bytes = [System.Convert]::FromBase64String('Ly8gT3BlbkNvZGUgaGFyZCBndWFyZCBmb3IgYmFja2VuZHMgdGhhdCBhY2NlcHQgYXQgbW9zdCBPTkUgaW1hZ2UgcGVyIG1vZGVsIHJlcXVlc3QuCi8vCi8vIFdoeSB0aGlzIGV4aXN0czoKLy8gT3BlbkNvZGUncyBidWlsdC1pbiBSZWFkIHRvb2wgc3RvcmVzIGltYWdlIG1lZGlhIHVuZGVyIGNvbXBsZXRlZCB0b29sLXJlc3VsdAovLyBhdHRhY2htZW50cy4gVGhvc2UgYXR0YWNobWVudHMgY2FuIHJlbWFpbiBpbiBjb252ZXJzYXRpb24gaGlzdG9yeSwgc28gYSBsYXRlcgovLyBpbWFnZSBSZWFkIGNhbiBjYXVzZSB0aGUgbmV4dCBwcm92aWRlciByZXF1ZXN0IHRvIGNvbnRhaW4gdGhlIG9sZCBpbWFnZSBwbHVzCi8vIHRoZSBuZXcgaW1hZ2UgZXZlbiB0aG91Z2ggdGhlIGFnZW50IGNhbGxlZCBSZWFkIG9ubHkgb25jZS4KLy8KLy8gVGhpcyBob29rIHJ1bnMgaW1tZWRpYXRlbHkgYmVmb3JlIHByb3ZpZGVyIG1lc3NhZ2UgY29udmVyc2lvbi4gSXQgcHJlc2VydmVzCi8vIG9ubHkgdGhlIG5ld2VzdCBpbWFnZSBhbnl3aGVyZSBpbiBhc3NlbWJsZWQgbWVzc2FnZSBoaXN0b3J5IGFuZCByZW1vdmVzIG9sZGVyCi8vIGltYWdlIG1lZGlhIGluLXBsYWNlLiBQcmlvciB0ZXh0dWFsIGFuYWx5c2lzIHJlbWFpbnMgaW4gdGhlIGNvbnZlcnNhdGlvbi4KLy8KLy8gSW5zdGFsbCBnbG9iYWxseSBhczoKLy8gICB+Ly5jb25maWcvb3BlbmNvZGUvcGx1Z2lucy9vbmUtaW1hZ2UtZ3VhcmQuanMKLy8KLy8gT3B0aW9uYWwgZGlhZ25vc3RpY3M6Ci8vICAgT1BFTkNPREVfT05FX0lNQUdFX0dVQVJEX0RFQlVHPTEKCmZ1bmN0aW9uIGlzSW1hZ2UoZmlsZSkgewogIGNvbnN0IG1pbWUgPSB0eXBlb2YgZmlsZT8ubWltZSA9PT0gInN0cmluZyIgPyBmaWxlLm1pbWUudG9Mb3dlckNhc2UoKSA6ICIiCiAgcmV0dXJuIG1pbWUuc3RhcnRzV2l0aCgiaW1hZ2UvIikKfQoKZXhwb3J0IGNvbnN0IE9uZUltYWdlR3VhcmQgPSBhc3luYyAoKSA9PiAoewogICJleHBlcmltZW50YWwuY2hhdC5tZXNzYWdlcy50cmFuc2Zvcm0iOiBhc3luYyAoX2lucHV0LCBvdXRwdXQpID0+IHsKICAgIGNvbnN0IG1lc3NhZ2VzID0gb3V0cHV0Py5tZXNzYWdlcwogICAgaWYgKCFBcnJheS5pc0FycmF5KG1lc3NhZ2VzKSkgcmV0dXJuCgogICAgLy8gcmVmcyBhcmUgY29sbGVjdGVkIGluIGNocm9ub2xvZ2ljYWwgbWVzc2FnZS9wYXJ0L2F0dGFjaG1lbnQgb3JkZXIuCiAgICAvLyBUaGUgZmluYWwgcmVmIGlzIHRoZXJlZm9yZSB0aGUgbmV3ZXN0IGltYWdlIGFuZCBpcyB0aGUgb25seSBvbmUgcmV0YWluZWQuCiAgICBjb25zdCByZWZzID0gW10KCiAgICBmb3IgKGNvbnN0IG1lc3NhZ2Ugb2YgbWVzc2FnZXMpIHsKICAgICAgY29uc3QgcGFydHMgPSBBcnJheS5pc0FycmF5KG1lc3NhZ2U/LnBhcnRzKSA/IG1lc3NhZ2UucGFydHMgOiBbXQoKICAgICAgZm9yIChsZXQgcGFydEluZGV4ID0gMDsgcGFydEluZGV4IDwgcGFydHMubGVuZ3RoOyBwYXJ0SW5kZXgrKykgewogICAgICAgIGNvbnN0IHBhcnQgPSBwYXJ0c1twYXJ0SW5kZXhdCgogICAgICAgIC8vIEltYWdlcyBhdHRhY2hlZCBkaXJlY3RseSB0byBhIHVzZXIgbWVzc2FnZS4KICAgICAgICBpZiAocGFydD8udHlwZSA9PT0gImZpbGUiICYmIGlzSW1hZ2UocGFydCkpIHsKICAgICAgICAgIHJlZnMucHVzaCh7CiAgICAgICAgICAgIGtpbmQ6ICJkaXJlY3QiLAogICAgICAgICAgICBtZXNzYWdlLAogICAgICAgICAgICBwYXJlbnQ6IHBhcnRzLAogICAgICAgICAgICBpbmRleDogcGFydEluZGV4LAogICAgICAgICAgfSkKICAgICAgICAgIGNvbnRpbnVlCiAgICAgICAgfQoKICAgICAgICAvLyBJbWFnZXMgcmV0dXJuZWQgYnkgdG9vbHMgc3VjaCBhcyBPcGVuQ29kZSdzIGJ1aWx0LWluIFJlYWQgdG9vbC4KICAgICAgICBpZiAoCiAgICAgICAgICBwYXJ0Py50eXBlID09PSAidG9vbCIgJiYKICAgICAgICAgIHBhcnQ/LnN0YXRlPy5zdGF0dXMgPT09ICJjb21wbGV0ZWQiICYmCiAgICAgICAgICBBcnJheS5pc0FycmF5KHBhcnQuc3RhdGUuYXR0YWNobWVudHMpCiAgICAgICAgKSB7CiAgICAgICAgICBjb25zdCBhdHRhY2htZW50cyA9IHBhcnQuc3RhdGUuYXR0YWNobWVudHMKCiAgICAgICAgICBmb3IgKGxldCBhdHRhY2htZW50SW5kZXggPSAwOyBhdHRhY2htZW50SW5kZXggPCBhdHRhY2htZW50cy5sZW5ndGg7IGF0dGFjaG1lbnRJbmRleCsrKSB7CiAgICAgICAgICAgIGlmICghaXNJbWFnZShhdHRhY2htZW50c1thdHRhY2htZW50SW5kZXhdKSkgY29udGludWUKCiAgICAgICAgICAgIHJlZnMucHVzaCh7CiAgICAgICAgICAgICAga2luZDogInRvb2wiLAogICAgICAgICAgICAgIG1lc3NhZ2UsCiAgICAgICAgICAgICAgcGFyZW50OiBhdHRhY2htZW50cywKICAgICAgICAgICAgICBpbmRleDogYXR0YWNobWVudEluZGV4LAogICAgICAgICAgICB9KQogICAgICAgICAgfQogICAgICAgIH0KICAgICAgfQogICAgfQoKICAgIGlmIChyZWZzLmxlbmd0aCA8PSAxKSByZXR1cm4KCiAgICBjb25zdCByZW1vdmVkRGlyZWN0TWVzc2FnZXMgPSBuZXcgU2V0KCkKICAgIGxldCByZW1vdmVkID0gMAoKICAgIC8vIFJlbW92ZSBpbiByZXZlcnNlIHRyYXZlcnNhbCBvcmRlciBzbyBzcGxpY2UgaW5kZXhlcyByZW1haW4gdmFsaWQuCiAgICAvLyBLZWVwIHJlZnNbcmVmcy5sZW5ndGggLSAxXSwgd2hpY2ggaXMgdGhlIG5ld2VzdCBpbWFnZS4KICAgIGZvciAobGV0IGkgPSByZWZzLmxlbmd0aCAtIDI7IGkgPj0gMDsgaS0tKSB7CiAgICAgIGNvbnN0IHJlZiA9IHJlZnNbaV0KICAgICAgcmVmLnBhcmVudC5zcGxpY2UocmVmLmluZGV4LCAxKQogICAgICByZW1vdmVkKysKCiAgICAgIGlmIChyZWYua2luZCA9PT0gImRpcmVjdCIpIHsKICAgICAgICByZW1vdmVkRGlyZWN0TWVzc2FnZXMuYWRkKHJlZi5tZXNzYWdlKQogICAgICB9CiAgICB9CgogICAgLy8gSWYgYW4gb2xkIHVzZXIgbWVzc2FnZSBjb25zaXN0ZWQgb25seSBvZiBhbiBpbWFnZSBhdHRhY2htZW50LCBzdHJpcHBpbmcKICAgIC8vIHRoYXQgYXR0YWNobWVudCB3b3VsZCBsZWF2ZSBhbiBlbXB0eSBwcm92aWRlciBtZXNzYWdlLiBSZW1vdmUgb25seSB0aG9zZQogICAgLy8gbWVzc2FnZXMgdGhhdCBiZWNhbWUgZW1wdHkgYmVjYXVzZSB0aGlzIGd1YXJkIHJlbW92ZWQgdGhlaXIgZGlyZWN0IGltYWdlLgogICAgZm9yIChsZXQgaSA9IG1lc3NhZ2VzLmxlbmd0aCAtIDE7IGkgPj0gMDsgaS0tKSB7CiAgICAgIGNvbnN0IG1lc3NhZ2UgPSBtZXNzYWdlc1tpXQogICAgICBpZiAoIXJlbW92ZWREaXJlY3RNZXNzYWdlcy5oYXMobWVzc2FnZSkpIGNvbnRpbnVlCiAgICAgIGlmIChBcnJheS5pc0FycmF5KG1lc3NhZ2UucGFydHMpICYmIG1lc3NhZ2UucGFydHMubGVuZ3RoID09PSAwKSB7CiAgICAgICAgbWVzc2FnZXMuc3BsaWNlKGksIDEpCiAgICAgIH0KICAgIH0KCiAgICBpZiAocHJvY2Vzcy5lbnYuT1BFTkNPREVfT05FX0lNQUdFX0dVQVJEX0RFQlVHID09PSAiMSIpIHsKICAgICAgY29uc29sZS5lcnJvcigKICAgICAgICBgW29uZS1pbWFnZS1ndWFyZF0gaW1hZ2VzPSR7cmVmcy5sZW5ndGh9IHJlbW92ZWQ9JHtyZW1vdmVkfSBrZXB0PTFgCiAgICAgICkKICAgIH0KICB9LAp9KQoKZXhwb3J0IGRlZmF1bHQgT25lSW1hZ2VHdWFyZAo=');" ^
  "[System.IO.File]::WriteAllBytes($path, $bytes);"

if not "%ERRORLEVEL%"=="0" (
    echo.
    echo ERROR: Failed to install the OpenCode one-image guard plugin.
    echo        Target: %ONE_IMAGE_GUARD_PATH%
    echo.
    exit /b 8
)


REM ============================================================================
REM 131K CONTEXT
REM ============================================================================
REM Total model context : 131,072
REM Compact reserve     : 16,384
REM Effective threshold : 114,688
REM Max response        : 8,192
REM ============================================================================

set "OPENCODE_5090_CONTEXT=131072"
set "OPENCODE_COMPACT_RESERVE=16384"
set "OPENCODE_COMPACT_AT=114688"
set "OPENCODE_MAX_OUTPUT_TOKENS=8192"

REM OpenCode experimental global output cap. The model definition below also
REM explicitly declares the 8,192-token output limit.
set "OPENCODE_EXPERIMENTAL_OUTPUT_TOKEN_MAX=8192"

REM Thinking ON. The model metadata below advertises reasoning=true to match
REM the vLLM endpoint, which is configured with Qwen3 reasoning enabled.

REM ============================================================================
REM LONG-RUN / LOCAL-MODEL TIMEOUTS
REM ============================================================================
REM Preserve the original 5090 launcher behavior:
REM   Request timeout : 6 hours
REM   Stream timeout  : 2 hours between streamed chunks
REM   Bash timeout    : 10 minutes default
REM ============================================================================

set "OPENCODE_REQUEST_TIMEOUT_MS=21600000"
set "OPENCODE_CHUNK_TIMEOUT_MS=7200000"
set "OPENCODE_EXPERIMENTAL_BASH_DEFAULT_TIMEOUT_MS=600000"

REM Temporary runtime files.
set "MODEL_FILE=%TEMP%\opencode-5090-model-%RANDOM%-%RANDOM%.tmp"
set "ENDPOINT_FILE=%TEMP%\opencode-5090-endpoint-%RANDOM%-%RANDOM%.tmp"
set "OPENCODE_CONFIG=%TEMP%\opencode-5090-config-%RANDOM%-%RANDOM%.json"

REM ============================================================================
REM AUTO-DETECT DIRECT RTX 5090 ENDPOINT
REM ============================================================================
REM Probe likely Docker Desktop mappings in preferred order:
REM   1) 127.0.0.1:8201       go-forward vLLM published port
REM   2) ${HOST_5090}:8201   same published port via LAN
REM   3) 127.0.0.1:8006       legacy/direct published port
REM   4) ${HOST_5090}:8006   legacy/direct LAN mapping
REM ============================================================================

echo.
echo =============================================================================
echo DIRECT RTX 5090 MODE  ^(OpenCode, direct backend, no router^)
echo =============================================================================
echo   GPU          : RTX 5090
echo   Runtime      : vLLM 0.28.0
echo   Context      : %OPENCODE_5090_CONTEXT%
echo   Compact at   : %OPENCODE_COMPACT_AT%
echo   Max response : %OPENCODE_MAX_OUTPUT_TOKENS%
echo   Thinking     : ON
echo   Image input  : ENABLED
echo   Image guard  : HARD MAX 1 IMAGE / PROVIDER REQUEST
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
    if exist "%OPENCODE_CONFIG%" del /q "%OPENCODE_CONFIG%" >nul 2>&1
    echo.
    echo Run this command to inspect Docker port publication:
    echo   docker ps --format "table {{.Names}}\t{{.Ports}}"
    echo.
    echo OpenCode was not started.
    exit /b %ENDPOINT_EXIT%
)

set /p "QWEN_5090_URL="<"%ENDPOINT_FILE%"
del /q "%ENDPOINT_FILE%" >nul 2>&1
set "OPENCODE_BASE_URL=%QWEN_5090_URL%/v1"

echo.
echo Selected backend: %QWEN_5090_URL%
echo.
echo Probing:
echo   %QWEN_5090_URL%/health
echo   %OPENCODE_BASE_URL%/models
echo.

REM ============================================================================
REM DISCOVER MODEL ID
REM ============================================================================

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference = 'Stop';" ^
  "$url = $env:QWEN_5090_URL.TrimEnd('/');" ^
  "try {" ^
  "  $null = Invoke-RestMethod -Uri ($url + '/health') -Method Get -TimeoutSec 60;" ^
  "} catch {" ^
  "  Write-Host '';" ^
  "  Write-Host ('ERROR: RTX 5090 vLLM became unreachable: ' + $url) -ForegroundColor Red;" ^
  "  Write-Host ('       ' + $_.Exception.Message) -ForegroundColor Yellow;" ^
  "  exit 2;" ^
  "};" ^
  "Write-Host 'RTX 5090 vLLM health: OK';" ^
  "try {" ^
  "  $response = Invoke-RestMethod -Uri ($url + '/v1/models') -Method Get -TimeoutSec 60;" ^
  "} catch {" ^
  "  Write-Host '';" ^
  "  Write-Host ('ERROR: RTX 5090 vLLM /v1/models unreachable: ' + $url) -ForegroundColor Red;" ^
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

set /p "OPENCODE_5090_MODEL="<"%MODEL_FILE%"
del /q "%MODEL_FILE%" >nul 2>&1

if not defined OPENCODE_5090_MODEL (
    echo.
    echo ERROR: Selected model ID was empty.
    if exist "%OPENCODE_CONFIG%" del /q "%OPENCODE_CONFIG%" >nul 2>&1
    exit /b 5
)

set "OPENCODE_MODEL=%OPENCODE_PROVIDER%/%OPENCODE_5090_MODEL%"

REM ============================================================================
REM BUILD ISOLATED OPENCODE CONFIG
REM ============================================================================
REM OpenCode's current stable/V1 config uses @ai-sdk/openai-compatible for
REM vLLM's /v1/chat/completions API and expects baseURL to end in /v1.
REM
REM Important behavior carried over from the Claude Code launcher:
REM   - explicit 131,072 context and 8,192 output limits
REM   - tool calling enabled
REM   - reasoning/thinking enabled
REM   - multimodal input advertised as text + image
REM   - image reads allowed; OpenCode can attach supported image media
REM   - attachment auto-resize capped at 1448x1448 (~2.097 MP square)
REM   - small_model pinned to this same local endpoint/model
REM   - compaction reserve 16,384 -> effective ~114,688-token threshold
REM   - all other permissions allowed; --auto approves non-denied actions
REM ============================================================================

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference = 'Stop';" ^
  "$model = $env:OPENCODE_5090_MODEL;" ^
  "$providerId = $env:OPENCODE_PROVIDER;" ^
  "$fullModel = $env:OPENCODE_MODEL;" ^
  "$models = [ordered]@{};" ^
  "$models[$model] = [ordered]@{" ^
  "  name = ('RTX 5090 Direct - ' + $model);" ^
  "  reasoning = $true;" ^
  "  tool_call = $true;" ^
  "  modalities = [ordered]@{ input = @('text','image'); output = @('text') };" ^
  "  limit = [ordered]@{ context = 131072; output = 8192 }" ^
  "};" ^
  "$providers = [ordered]@{};" ^
  "$providers[$providerId] = [ordered]@{" ^
  "  npm = '@ai-sdk/openai-compatible';" ^
  "  name = 'RTX 5090 vLLM Direct';" ^
  "  options = [ordered]@{" ^
  "    baseURL = $env:OPENCODE_BASE_URL;" ^
  "    timeout = [int64]$env:OPENCODE_REQUEST_TIMEOUT_MS;" ^
  "    chunkTimeout = [int64]$env:OPENCODE_CHUNK_TIMEOUT_MS" ^
  "  };" ^
  "  models = $models" ^
  "};" ^
  "$readRules = [ordered]@{};" ^
  "$readRules['*'] = 'allow';" ^
  "$permission = [ordered]@{};" ^
  "$permission['*'] = 'allow';" ^
  "$permission['read'] = $readRules;" ^
  "$attachment = [ordered]@{ image = [ordered]@{ auto_resize = $true; max_width = 1448; max_height = 1448; max_base64_bytes = 5242880 } };" ^
  "$config = [ordered]@{" ^
  "  '$schema' = 'https://opencode.ai/config.json';" ^
  "  model = $fullModel;" ^
  "  small_model = $fullModel;" ^
  "  enabled_providers = @($providerId);" ^
  "  compaction = [ordered]@{ auto = $true; prune = $false; reserved = 16384 };" ^
  "  permission = $permission;" ^
  "  attachment = $attachment;" ^
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
echo   Upstream ID:    %OPENCODE_5090_MODEL%
echo   Endpoint:       %OPENCODE_BASE_URL%/chat/completions
echo   Backend:        RTX 5090 DIRECT - NO ROUTER
echo   Direct URL:     %QWEN_5090_URL%
echo   Runtime:        vLLM 0.28.0
echo   Total context:  %OPENCODE_5090_CONTEXT% tokens
echo   Compact window: %OPENCODE_COMPACT_AT% tokens ^(16,384 reserve^)
echo   Max response:   %OPENCODE_MAX_OUTPUT_TOKENS% tokens
echo   Thinking:       ON
echo   Image input:    ENABLED ^(PNG/JPEG/GIF/WebP attachments^)
echo   Image guard:    HARD MAX 1 IMAGE / PROVIDER REQUEST
echo   API timeout:    6 hours/request
echo   Stream idle:    2 hours between chunks
echo   Bash timeout:   10 minutes default
echo   Permissions:    AUTO / unrestricted
echo   Config file:    %OPENCODE_CONFIG%
echo   Runtime config: INLINE OVERRIDE ACTIVE
echo   Vision guard:   %ONE_IMAGE_GUARD_PATH%
echo   CLI:            %REAL_OPENCODE%
echo =============================================================================
echo.
echo EXPECTED CONTEXT:
echo   OpenCode should report a 131,072-token model context.
echo   Automatic compaction reserves 16,384 tokens, yielding an effective
echo   threshold of approximately 114,688 tokens.
echo.
echo WARNING: OpenCode can modify, delete, and execute files without approval.
echo          Vision requests consume additional VRAM; the backend limits image count/size.
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
