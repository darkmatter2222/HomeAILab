# List visible top-level window titles (proven EnumWindows recipe from verify-deck-physical.ps1).
Add-Type -TypeDefinition 'using System; using System.Runtime.InteropServices; using System.Text; public class Win32List { public delegate bool EnumCb(IntPtr h, IntPtr l); [DllImport("user32.dll")] public static extern bool EnumWindows(EnumCb cb, IntPtr l); [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr h, StringBuilder s, int n); [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h); [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h); }'

$script:titled = New-Object System.Collections.Generic.List[object]
[void][Win32List]::EnumWindows({
    param($h, $l)
    $sb = New-Object System.Text.StringBuilder 256
    [void][Win32List]::GetWindowText($h, $sb, 256)
    if ([Win32List]::IsWindowVisible($h) -and $sb.Length -gt 0) {
        $script:titled.Add([Win32List]::GetWindowThreadProcessId($h).ToString() + "`t" + $sb.ToString())
    }
    return $true
}, [IntPtr]::Zero)
$script:titled | ForEach-Object { $_ }
