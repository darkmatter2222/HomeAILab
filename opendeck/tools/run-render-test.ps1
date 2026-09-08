# run-render-test.ps1 — Side Quest A orchestration:
# 1. stop the live opendeck plugin via the Elgato CLI (host-managed stop)
# 2. run tools/deck-render-test.mjs for N seconds (registers on the SDK port,
#    collects willAppear contexts, pushes RED/GREEN/BLUE/rainbow/OFF/IDLE keys,
#    then cycles colors every 1s)
# 3. screenshot the physical deck (Stream Deck app mirror) at t+4s and t+8s
# 4. restart the plugin via the Elgato CLI
param([int]$Seconds = 12)

$ErrorActionPreference = "Stop"
Set-Location "C:\Users\ryans\source\repos\HomeAILab\opendeck"
Add-Type -AssemblyName System.Windows.Forms, System.Drawing

function Capture-Screen([string]$path) {
  $bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
  $bmp = New-Object System.Drawing.Bitmap($bounds.Width, $bounds.Height)
  $g = [System.Drawing.Graphics]::FromImage($bmp)
  $g.CopyFromScreen($bounds.X, $bounds.Y, 0, 0, $bounds.Size)
  $g.Dispose()
  $bmp.Save($path, [System.Drawing.Imaging.ImageFormat]::Png)
  $bmp.Dispose()
  Write-Output ("screenshot saved: " + $path)
}

$cli = "node_modules/@elgato/cli/bin/streamdeck.mjs"
$uuid = "dev.ryans.opendeck"

# 1. stop the live plugin (host-managed)
Write-Output ("stopping plugin via CLI: streamdeck stop " + $uuid)
node $cli stop $uuid
Start-Sleep -Seconds 1

# 2. run the render test in a background job
$job = Start-Job {
  Set-Location "C:\Users\ryans\source\repos\HomeAILab\opendeck"
  node tools/deck-render-test.mjs $Using:Seconds 2>&1 | Tee-Object -FilePath tools/deck-render-test.log
}

# 3. screenshots during the run, timed to the push log:
#    static images are pushed at t+4.2s  -> screenshot at t+4.6s
#    cycle frames: GREEN t+5.2, BLUE t+6.2, AMBER t+7.2, GRAY t+8.2, RED t+9.2
#    -> screenshots at t+6.6s (BLUE frame) and t+8.6s (GRAY frame)
# After each capture, run the physical-deck verifier: it brings the Stream
# Deck app to the front, re-captures, and scans the app window (device mirror)
# for the target colors.
Start-Sleep -Seconds 4
Start-Sleep -Milliseconds 600
Capture-Screen "C:\Users\ryans\source\repos\HomeAILab\opendeck\test\deck-shot-static.png"
powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -File tools/verify-deck-physical.ps1 -ShotPath "C:\Users\ryans\source\repos\HomeAILab\opendeck\test\deck-shot-static-verify.png"
Start-Sleep -Seconds 2
Start-Sleep -Milliseconds 600
Capture-Screen "C:\Users\ryans\source\repos\HomeAILab\opendeck\test\deck-shot-cycle-blue.png"
powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -File tools/verify-deck-physical.ps1 -ShotPath "C:\Users\ryans\source\repos\HomeAILab\opendeck\test\deck-shot-cycle-blue-verify.png"
Start-Sleep -Seconds 2
Start-Sleep -Milliseconds 600
Capture-Screen "C:\Users\ryans\source\repos\HomeAILab\opendeck\test\deck-shot-cycle.png"
powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -File tools/verify-deck-physical.ps1 -ShotPath "C:\Users\ryans\source\repos\HomeAILab\opendeck\test\deck-shot-cycle-verify.png"

Wait-Job $job -Timeout 60 | Out-Null
Write-Output "=== render test log ==="
Get-Content tools\deck-render-test.log

# 4. restart the plugin (host launches it and sends willAppear for the front-page keys)
Write-Output ("restarting plugin via CLI")
node $cli restart $uuid
Start-Sleep -Seconds 2
$check = Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'node.exe' -and $_.CommandLine -like '*opendeck*' } | Select-Object -First 1
if ($check) { Write-Output ("plugin restarted: PID " + $check.ProcessId) }
else { Write-Output "WARNING: plugin process not found after restart" }
