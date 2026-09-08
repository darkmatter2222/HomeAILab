# Get the foreground window title (P/Invoke GetForegroundWindow + GetWindowTextW)
Add-Type -TypeDefinition 'using System; using System.Runtime.InteropServices; using System.Text; public class Win32Fg { [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow(); [DllImport("user32.dll")] public static extern int GetWindowTextW(IntPtr h, StringBuilder s, int n); }'
$h = [Win32Fg]::GetForegroundWindow()
$sb = New-Object System.Text.StringBuilder 512
[void][Win32Fg]::GetWindowTextW($h, $sb, 512)
$sb.ToString()
