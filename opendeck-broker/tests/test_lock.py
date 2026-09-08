import os
import subprocess
import sys
from pathlib import Path

from opendeck_broker.lock import BrokerLock


def test_named_mutex_excludes_a_second_process():
    # research section 7: "One broker is the single writer; OS named mutex." The
    # same-process test below proves the ERROR_ALREADY_EXISTS path; this proves a
    # genuinely separate process is excluded too (the actual "one device owner").
    parent = BrokerLock()
    assert parent.acquire() is True
    code = (
        "from opendeck_broker.lock import BrokerLock; "
        "import sys; sys.exit(0 if not BrokerLock().acquire() else 1)"
    )
    pkg = Path(__file__).resolve().parents[1]
    env = {**os.environ, "PYTHONPATH": str(pkg)}
    r = subprocess.run([sys.executable, "-c", code], env=env,
                       capture_output=True, timeout=90)
    assert r.returncode == 0, r.stderr  # child rejected -> exit 0
    parent.release()


def test_single_instance_lock_excludes_second():
    a = BrokerLock()
    b = BrokerLock()
    assert a.acquire() is True
    # a second broker must be rejected while the first holds the lock
    assert b.acquire() is False
    a.release()
    # after release, the second can acquire
    assert b.acquire() is True
    b.release()


def test_release_is_idempotent_enough_to_reacquire():
    a = BrokerLock()
    assert a.acquire() is True
    a.release()
    c = BrokerLock()
    assert c.acquire() is True
    c.release()
