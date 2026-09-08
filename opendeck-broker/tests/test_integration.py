"""Integration: real main.build_stack + real DbObserver + real broker render.

Exercises the actual wiring (main.py) end-to-end against a real temp SQLite DB
with a mock device -- the path previously only smoke-tested via --mock --once.
"""

import json
import os
import sqlite3
import time

from opendeck_broker.config import Config
from opendeck_broker.main import build_stack
from opendeck_broker.model import DisplayAppearance

LIVE = os.getpid()


def now_ms():
    return int(time.time() * 1000)


def make_db(tmp_path, directory="/d/homeai", recent=True, tool_status="running"):
    db = tmp_path / "opencode.db"
    conn = sqlite3.connect(str(db))
    conn.execute(
        "CREATE TABLE session (id TEXT PRIMARY KEY, directory TEXT, title TEXT,"
        " time_created INTEGER, time_updated INTEGER, time_archived INTEGER)"
    )
    conn.execute(
        "CREATE TABLE part (id TEXT PRIMARY KEY, session_id TEXT, time_updated INTEGER, data TEXT)"
    )
    t = now_ms() if recent else now_ms() - 120_000
    conn.execute(
        "INSERT INTO session(id, directory, title, time_created, time_updated, time_archived)"
        " VALUES(?,?,?,?,?,?)",
        ("s1", directory, "title", t, t, None),
    )
    conn.execute(
        "INSERT INTO part(id, session_id, time_updated, data) VALUES(?,?,?,?)",
        ("p1", "s1", t, json.dumps({"type": "tool", "tool": "bash", "state": {"status": tool_status}})),
    )
    conn.commit()
    conn.close()
    return db


def run_ticks(stack, n=3):
    for _ in range(n):
        stack.adapter.refresh()
        stack.broker.render()
        stack.broker.process_presses()


def test_busy_session_renders_green(tmp_path):
    db = make_db(tmp_path, recent=True)
    cfg = Config(db_path=db, port=0)
    stack = build_stack(config=cfg, use_mock=True)
    iid, slot = stack.adapter.register_launch("/d/homeai", "homeai", pid=LIVE)
    stack.broker.start()
    run_ticks(stack)
    assert stack.broker.registry.frame()[slot].appearance is DisplayAppearance.RUN
    # the mock device actually received a render for that slot
    assert stack.device.images.get(slot) is not None


def test_idle_session_renders_amber(tmp_path):
    # old part update AND a completed tool -> not busy (amber)
    db = make_db(tmp_path, recent=False, tool_status="completed")
    cfg = Config(db_path=db, port=0)
    stack = build_stack(config=cfg, use_mock=True)
    _, slot = stack.adapter.register_launch("/d/homeai", "homeai", pid=LIVE)
    stack.broker.start()
    run_ticks(stack)
    assert stack.broker.registry.frame()[slot].appearance is DisplayAppearance.IDLE


def test_home_screen_no_session_renders_amber(tmp_path):
    # DB exists but has no session for this directory -> amber, not black
    db = make_db(tmp_path, directory="/d/other")
    cfg = Config(db_path=db, port=0)
    stack = build_stack(config=cfg, use_mock=True)
    _, slot = stack.adapter.register_launch("/d/homeai", "homeai", pid=LIVE)
    stack.broker.start()
    run_ticks(stack)
    assert stack.broker.registry.frame()[slot].appearance is DisplayAppearance.IDLE


def test_dead_process_clears_slot_via_real_loop(tmp_path):
    db = make_db(tmp_path, recent=True)
    cfg = Config(db_path=db, port=0)
    stack = build_stack(config=cfg, use_mock=True)
    # a process that is already dead
    import subprocess
    import sys

    p = subprocess.Popen([sys.executable, "-c", "pass"])
    p.wait()
    _, slot = stack.adapter.register_launch("/d/homeai", "homeai", pid=p.pid)
    stack.broker.start()
    run_ticks(stack)
    assert stack.broker.registry.frame()[slot].appearance is DisplayAppearance.BLACK


def test_run_entry_point_tick_loop_and_lock_cleanup(tmp_path):
    # the real entry point (main.run), not just build_stack: it acquires the
    # single-writer lock, opens the device + starts the API, runs the full tick
    # loop (poll -> refresh -> sweep -> render -> process_presses) for a bounded
    # number of ticks, then releases the lock and stops the API + broker.
    from opendeck_broker.lock import BrokerLock
    from opendeck_broker.main import run

    db = make_db(tmp_path)
    cfg = Config(db_path=db, port=0)
    rc = run(config=cfg, use_mock=True, tick=0.01, max_ticks=3)
    assert rc == 0
    # the single-writer lock must be released so a second broker can start
    lock = BrokerLock()
    assert lock.acquire() is True
    lock.release()
