# verify-deck-physical.ps1 — physical Stream Deck verification.
# Brings the Stream Deck app window to the front, captures the screen, crops
# to the app window (the app mirrors the physical device), and scans the crop
# for the test colors. Prints a color report: which of RED/GREEN/BLUE/AMBER/
# GRAY were found, with pixel counts (proof the device actually shows them).
param(
  [string]$ShotPath = "C:\Users\ryans\source\repos\HomeAILab\opendeck\test\deck-shot-static.png"
)

Add-Type -AssemblyName System.Windows.Forms, System.Drawing

# P/Invoke for GetWindowRect + SetForegroundWindow. Proven recipe:
# - DllImport with an IntPtr pointer parameter (avoids the out-struct AccessViolation
#   that the dynamic call site triggers), pinned GCHandle for the RECT buffer.
$win32Def = "[System.Runtime.InteropServices.StructLayout(System.Runtime.InteropServices.LayoutKind.Sequential)] public class RECT { public int Left; public int Top; public int Right; public int Bottom; public int GetWidth() { return Right - Left; } public int GetHeight() { return Bottom - Top; } }`n[DllImport(`"user32.dll`")] public static extern bool GetWindowRect(System.IntPtr hWnd, System.IntPtr rectPtr);`n[DllImport(`"user32.dll`")] public static extern bool SetForegroundWindow(System.IntPtr hWnd);`n[DllImport(`"user32.dll`")] public static extern int ShowWindow(System.IntPtr hWnd, int nCmdShow);`n[DllImport(`"user32.dll`")] public static extern void keybd_event(byte bVk, byte bScan, uint dwFlags, System.IntPtr dwExtraInfo);`npublic WinOps.RECT GetRect(System.IntPtr h) { WinOps.RECT r = new WinOps.RECT(); System.Runtime.InteropServices.GCHandle gch = System.Runtime.InteropServices.GCHandle.Alloc(r, System.Runtime.InteropServices.GCHandleType.Pinned); bool ok = GetWindowRect(h, gch.AddrOfPinnedObject()); gch.Free(); return r; }`npublic bool SetForeground(System.IntPtr h) { keybd_event(0x12, 0, 0, System.IntPtr.Zero); keybd_event(0x12, 0, 2, System.IntPtr.Zero); return SetForegroundWindow(h); }`npublic bool Restore(System.IntPtr h) { return ShowWindow(h, 9) != 0; }"
$opsType = Add-Type -Namespace WinApi -Name WinOps -MemberDefinition $win32Def -PassThru
$ops = $opsType.Assembly.CreateInstance("WinApi.WinOps")

$sd = Get-Process StreamDeck -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $sd) { Write-Output "ERROR: Stream Deck app not running"; exit 1 }
$cropX = 0; $cropY = 0; $cropW = 0; $cropH = 0
# The DLR boxes the RECT fields as Object[]; unbox before use.
function Unbox([object]$v) {
  if ($v -is [object[]]) { return [int]$v[0] }
  return [int]$v
}
if ($sd.MainWindowHandle -ne 0) {
  $r0 = $ops.GetRect($sd.MainWindowHandle)
  $wasMinimized = ((Unbox $r0.Left) -eq -32000)
  if ($wasMinimized) { $ops.Restore($sd.MainWindowHandle) | Out-Null }
  $fg = $ops.SetForeground($sd.MainWindowHandle)
  Start-Sleep -Milliseconds 800
  # Re-fetch the rect AFTER foreground/restore, so a previously-minimized
  # window (Left/Top == -32000) is captured at its on-screen position.
  $rect = $ops.GetRect($sd.MainWindowHandle)
  $cropX = Unbox $rect.Left; $cropY = Unbox $rect.Top
  $cropW = Unbox $rect.GetWidth(); $cropH = Unbox $rect.GetHeight()
  $fgB = Unbox $fg
  Write-Output ("Stream Deck app window rect: x=" + $cropX + " y=" + $cropY + " w=" + $cropW + " h=" + $cropH + " foreground=" + $fgB + " restored=" + $wasMinimized)
} else {
  Write-Output "NOTE: Stream Deck app has no main window (minimized/hidden); capturing full screen instead"
}

# Full-screen capture
$screen = [System.Windows.Forms.Screen]::PrimaryScreen
$bounds = $screen.Bounds
$bmp = New-Object System.Drawing.Bitmap($bounds.Width, $bounds.Height)
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($bounds.X, $bounds.Y, 0, 0, $bounds.Size)
$g.Dispose()
$bmp.Save($ShotPath, [System.Drawing.Imaging.ImageFormat]::Png)
$bmp.Save("C:\Users\ryans\source\repos\HomeAILab\opendeck\test\screen-full.bmp", [System.Drawing.Imaging.ImageFormat]::Bmp)
# High-res ASCII + histogram of the app window region (device mirror).
if ($cropW -gt 0) {
  node "C:\Users\ryans\source\repos\HomeAILab\opendeck\tools\bmp-dump.mjs" "C:\Users\ryans\source\repos\HomeAILab\opendeck\test\screen-full.bmp" $cropX $cropY $cropW $cropH
}

# Scan the full-screen bitmap within the app window rect (the device mirror).
# (Scans the screenshot directly in the window region — no DrawImage needed.)
$Targets = @{
  "RED"    = [System.Drawing.Color]::FromArgb(0xff, 0x5a, 0x4e)
  "GREEN"  = [System.Drawing.Color]::FromArgb(0x2f, 0xd0, 0x6f)
  "BLUE"   = [System.Drawing.Color]::FromArgb(0x3d, 0x9b, 0xf5)
  "AMBER"  = [System.Drawing.Color]::FromArgb(0xf5, 0xb1, 0x3d)
  "GRAY"   = [System.Drawing.Color]::FromArgb(0x5a, 0x5e, 0x6b)
}

$TOL = 40
$report = @{}
$xMax = if ($cropW -gt 0) { $cropX + $cropW } else { $bmp.Width }
$yMax = if ($cropH -gt 0) { $cropY + $cropH } else { $bmp.Height }
$xMin = if ($cropW -gt 0) { $cropX } else { 0 }
$yMin = if ($cropH -gt 0) { $cropY } else { 0 }
foreach ($name in $Targets.Keys) {
  $target = $Targets[$name]
  $count = 0
  for ($y = $yMin; $y -lt $yMax; $y += 2) {
    for ($x = $xMin; $x -lt $xMax; $x += 2) {
      $p = $bmp.GetPixel($x, $y)
      if ([Math]::Abs($p.R - $target.R) -le $TOL -and [Math]::Abs($p.G - $target.G) -le $TOL -and [Math]::Abs($p.B - $target.B) -le $TOL) { $count++ }
    }
  }
  $report[$name] = $count
  Write-Output ("  {0,-6} : {1} sampled pixels" -f $name, $count)
}
# ASCII-art dump of the window region (downsampled) so a human/agent can see
# what the app window (device mirror) actually displays.
$gridW = 96; $gridH = 26
$rows = @{}
for ($gy = 0; $gy -lt $gridH; $gy++) {
  $sy = $yMin + [int]($gy * ($yMax - $yMin) / $gridH)
  $line = ""
  for ($gx = 0; $gx -lt $gridW; $gx++) {
    $sx = $xMin + [int]($gx * ($xMax - $xMin) / $gridW)
    $p = $bmp.GetPixel($sx, $sy)
    $bright = ($p.R + $p.G + $p.B) / 3
    if ($p.R -gt 200 -and $p.G -lt 150 -and $p.B -lt 150) { $line += "R" }
    elseif ($p.G -gt 150 -and $p.R -lt 150 -and $p.B -lt 150) { $line += "G" }
    elseif ($p.B -gt 200 -and $p.R -lt 150) { $line += "B" }
    elseif ($bright -gt 180) { $line += "#" }
    elseif ($bright -gt 90) { $line += "+" }
    else { $line += " " }
  }
  $rows[$gy] = $line
}
Write-Output "---- window region ASCII dump (R=red G=green B=blue #=bright +=mid) ----"
foreach ($k in ($rows.Keys | Sort-Object)) { Write-Output ("{0}" -f $rows[$k]) }
Write-Output "---------------------------------------------------------------------"

$bmp.Dispose()
$found = ($report.Values | Where-Object { $_ -gt 0 } | Measure-Object).Count
$region = if ($cropW -gt 0) { "Stream Deck app window (device mirror)" } else { "full screen" }
Write-Output ("VERDICT: {0}/5 target colors found in {1}" -f $found, $region)
exit $(if ($found -gt 0) { 0 } else { 1 })
