# Close terminal windows whose title contains the given marker (e.g. "opencode:homeai").
# Usage: powershell -File close-marked.ps1 <marker>
param([string]$Marker)

Add-Type -TypeDefinition 'using System; using System.Runtime.InteropServices; using System.Text; public class Win32Cls { public delegate bool EnumCb(IntPtr h, IntPtr l); [DllImport("user32.dll")] public static extern bool EnumWindows(EnumCb cb, IntPtr l); [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr h, StringBuilder s, int n); [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h); [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h); }'

$marker = $Marker.ToLower()
$pids = New-Object System.Collections.Generic.List[System.UInt32]

$script:pids = $pids
[void][Win32Cls]::EnumWindows({
    param($h, $l)
    $sb = New-Object System.Text.StringBuilder 512
    [void][Win32Cls]::GetWindowText($h, $sb, 512)
    if ([Win32Cls]::IsWindowVisible($h) -and $sb.ToString().ToLower().Contains($marker)) {
        $pids.Add([Win32Cls]::GetWindowThreadProcessId($h))
        return $false
    }
    return $true
}, [IntPtr]::Zero)

$killed = 0
foreach ($pid in ($pids | Select-Object -Unique)) {
    $r = Start-Process taskkill -ArgumentList "/F", "/PID", $pid.ToString() -PassThru -Wait -NoNewWindow
    if ($r.ExitCode -eq 0) { $killed++ }
}
Write-Output $killed
