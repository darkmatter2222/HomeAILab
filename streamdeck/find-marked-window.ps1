# Check whether any visible window title contains the given marker
# (the proven single-line EnumWindows recipe from verify-deck-physical.ps1).
param([string]$Marker)

Add-Type -TypeDefinition 'using System; using System.Runtime.InteropServices; using System.Text; public class W { public delegate bool EP(IntPtr h, IntPtr l); [DllImport("user32.dll")] public static extern bool EnumWindows(EP cb, IntPtr l); [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr h, StringBuilder s, int n); [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h); }'
$target = $Marker.ToLower()
$script:found = [IntPtr]::Zero
$script:foundTitle = ""
[void][W]::EnumWindows({ param($h, $l) $sb = New-Object System.Text.StringBuilder 512; [void][W]::GetWindowText($h, $sb, 512); if ([W]::IsWindowVisible($h) -and $sb.ToString().ToLower().Contains($target)) { $script:found = $h; $script:foundTitle = $sb.ToString(); return $false }; return $true }, [IntPtr]::Zero)
if ($script:found -ne [IntPtr]::Zero) {
    Write-Output "FOUND:" + $script:foundTitle
} else {
    Write-Output "NOTFOUND"
}
