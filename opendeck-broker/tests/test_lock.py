import os
import subprocess
import sys
import tempfile
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


def test_release_without_acquire_is_safe():
    # release() before any acquire() is a defensive no-op (no held handle /
    # lockfile), not a crash -- a broker that failed to start still shuts down
    # cleanly.
    b = BrokerLock()
    b.release()  # must not raise
    b.release()  # and a second release is equally safe


def test_lockfile_fallback_excludes_and_releases(monkeypatch, tmp_path):
    # the portable lockfile path (non-Windows) must exclude a second instance
    # and clean up its lockfile on release so a later broker can acquire.
    # (the private methods are exercised directly; they carry no os.name check,
    # so the Windows pathlib flavor is left intact)
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
    lockfile = tmp_path / "opendeck-broker.lock"

    a = BrokerLock()
    assert a._acquire_lockfile() is True
    assert lockfile.exists()  # lockfile created
    b = BrokerLock()
    assert b._acquire_lockfile() is False  # lockfile exists -> rejected
    a._release_lockfile()
    assert lockfile.exists() is False  # release removed it
    c = BrokerLock()
    assert c._acquire_lockfile() is True  # reacquirable after release
    c._release_lockfile()
