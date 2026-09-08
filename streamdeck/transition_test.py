"""Live transition test: drive a real OpenCode session through
OFF -> IDLE -> RUNNING -> WAITING -> IDLE and, after each transition,
scan the Stream Deck mirror to confirm the on-device color follows the real state.

Usage:
  python streamdeck/transition_test.py
"""

import json
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MIRROR_SCAN_PS1 = REPO / "opendeck" / "tools" / "verify-deck-physical.ps1"
SERVE_BASE = "http://127.0.0.1:4202"
HOMEAI_DIR = "C:/Users/ryans/source/repos/HomeAILab"
DECK_SETTLE_S = 3.0

# The project slot for HomeAILab on the Mini (projects.json order: homeai=slot 0).
# The scan reports aggregate colors, so we verify by expected color presence.
STATE_COLOR_NAME = {
    "running": "GREEN",
    "idle": "AMBER",
    "waiting": "RED",
    "off": "GRAY",
}


def serve_req(method, path, body=None, timeout=10.0):
    url = SERVE_BASE + path
    data = json.dumps(body).encode() if body is not None else None
    headers = {"content-type": "application/json"} if data else {}
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
        return json.loads(raw.decode()) if raw else {}


def scan_colors(timeout=120):
    out = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(MIRROR_SCAN_PS1)],
        capture_output=True, text=True, timeout=timeout,
    )
    counts = {}
    for line in out.stdout.splitlines():
        m = re.match(r"^(RED|GREEN|BLUE|AMBER|GRAY)\s*:\s*(\d+)\s*sampled pixels", line.strip())
        if m:
            counts[m.group(1)] = int(m.group(2))
    return counts


def wait_for_color(target, timeout_s=30, poll=2.0):
    end = time.time() + timeout_s
    last = None
    while time.time() < end:
        counts = scan_colors()
        last = counts
        if counts.get(target, 0) > 0:
            return True, counts
        time.sleep(poll)
    return (last or {}).get(target, 0) > 0, last or {}


def send_bg(sid, text):
    import threading
    def _send():
        try:
            serve_req("POST", f"/session/{sid}/message",
                      {"parts": [{"type": "text", "text": text}], "model": None}, 240.0)
        except Exception:
            pass
    threading.Thread(target=_send, daemon=True).start()


def find_question(sid, timeout=60.0):
    end = time.time() + timeout
    while time.time() < end:
        qs = serve_req("GET", "/question", timeout=5.0)
        for q in (qs if isinstance(qs, list) else []):
            if q.get("sessionID") == sid:
                return q["id"]
        time.sleep(2.0)
    return None


def main() -> int:
    # 1) OFF -> IDLE
    sid = serve_req("POST", "/session", {"directory": HOMEAI_DIR, "title": "transition test"})["id"]
    time.sleep(DECK_SETTLE_S)
    ok_idle, c_idle = wait_for_color("AMBER", 30)
    print(f"[1] OFF->IDLE  device shows AMBER: {ok_idle}  {c_idle}")

    # 2) IDLE -> RUNNING (send a small prompt)
    send_bg(sid, "Reply with exactly: ok")
    time.sleep(3.0)
    ok_run, c_run = wait_for_color("GREEN", 30)
    print(f"[2] IDLE->RUNNING  device shows GREEN: {ok_run}  {c_run}")

    # 3) RUNNING -> WAITING (ask a question)
    send_bg(sid, "Use your question tool to ask me one yes/no question: is the deck red? Wait for my answer.")
    qid = find_question(sid, 60.0)
    time.sleep(DECK_SETTLE_S)
    ok_wait, c_wait = wait_for_color("RED", 30)
    print(f"[3] RUNNING->WAITING  device shows RED: {ok_wait}  (question={qid})  {c_wait}")

    # 4) WAITING -> RUNNING -> IDLE (answer the question)
    if qid:
        serve_req("POST", f"/question/{qid}/reply", {"answers": [["Yes"]], }, timeout=30.0)
    time.sleep(15.0)  # let the post-answer turn finish -> idle
    ok_final, c_final = wait_for_color("AMBER", 45)
    print(f"[4] WAITING->IDLE  device shows AMBER: {ok_final}  {c_final}")

    ok = ok_idle and ok_run and ok_wait and ok_final
    print("\nVERDICT:", "PASS — device tracks real state through transitions" if ok
          else "FAIL — device did not track a transition")
    try:
        serve_req("DELETE", f"/session/{sid}")
    except Exception:
        pass
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
