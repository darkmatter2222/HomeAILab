import subprocess, traceback, os, sys
sys.path.insert(0, r'C:\Users\ryans\source\repos\HomeAILab\streamdeck')
import acceptance as a
REPO = a.REPO

# Reproduce the exact npx call from tc_051
try:
    out = subprocess.run(
        ["npx", "-y", "@elgato/cli", "restart", "dev.ryans.opendeck"],
        capture_output=True, text=True, timeout=120, cwd=str(REPO / "opendeck"),
    )
    print("npx OK, rc=", out.returncode)
    print("stdout:", out.stdout.strip()[-300:])
    print("stderr:", out.stderr.strip()[-300:])
except Exception as e:
    print("npx RAISED:", type(e).__name__, str(e))
    traceback.print_exc()
