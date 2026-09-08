"""Run acceptance test cases in batches with a cumulative report.

Usage:
    python streamdeck/batch.py TC-001 TC-002 ...

Each TC is executed via the Harness; after every TC the cumulative
report (results + log + latencies) is written, so even if the enclosing
shell command times out, partial results are persisted.
"""
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import acceptance as a

KEEP_SESSION = "ses_f913cd0f2ffeZglY2RzKnCMBj0"


def main() -> int:
    tc_ids = [t.upper() for t in sys.argv[1:]]
    if not tc_ids:
        print("usage: batch.py TC-xxx [TC-yyy ...]")
        return 2
    h = a.Harness(serve_base=a.SERVE_BASE, keep_session=KEEP_SESSION)
    jf = HERE / "acceptance-report.json"
    prev_results = {}
    if jf.exists():
        try:
            prev = json.loads(jf.read_text(encoding="utf-8"))
            prev_results = prev.get("results", {}) or {}
            # Carry latency samples forward so the final report can state the
            # latency distribution (goal: "record transition latency").
            h.latencies = prev.get("latencies", []) or []
        except Exception:
            prev_results = {}
    results = dict(prev_results)
    tc_004_sid = None
    for tc in tc_ids:
        fn = getattr(h, tc.lower().replace("tc-", "tc_"), None)
        if fn is None:
            print(f"{tc}: unknown test case, skipping")
            continue
        if tc == "TC-004":
            tc_004_sid = fn()
        elif tc == "TC-007":
            # TC-007 completes the session that TC-004 started. If it isn't
            # in this batch, create the session via tc_004() so the test has
            # a real RUNNING session to observe complete to IDLE.
            if tc_004_sid is None:
                tc_004_sid = h.tc_004()
            sid = tc_004_sid
            try:
                ok = bool(fn(sid) if sid else False)
            except Exception as e:
                ok = False
                h.record(tc, pass_=False, error=str(e))
        elif tc == "TC-041":
            try:
                ok = bool(fn(3))
            except Exception as e:
                ok = False
                h.record(tc, pass_=False, error=str(e))
        else:
            try:
                ok = bool(fn())
            except Exception as e:
                ok = False
                h.record(tc, pass_=False, error=str(e))
        results[tc] = ok
        print(f"{tc}: {'PASS' if ok else 'FAIL'}")
        h.write_report(results)  # cumulative: previous + new
    failed = [tc for tc, ok in results.items() if not ok]
    passed = sum(1 for ok in results.values() if ok)
    print(f"{passed}/{len(results)} passed; failed: {failed or 'none'}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
