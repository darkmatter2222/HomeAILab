import json
import sqlite3
import time

from opendeck_broker.model import Status
from opendeck_broker.opencode.observe import DbObserver


def now_ms():
    return int(time.time() * 1000)


def make_db(tmp_path):
    db = tmp_path / "opencode.db"
    conn = sqlite3.connect(str(db))
    conn.execute(
        "CREATE TABLE session (id TEXT PRIMARY KEY, directory TEXT, title TEXT,"
        " time_created INTEGER, time_updated INTEGER, time_archived INTEGER)"
    )
    conn.execute(
        "CREATE TABLE part (id TEXT PRIMARY KEY, session_id TEXT, time_updated INTEGER,"
        " data TEXT)"
    )
    return db, conn


def add_session(conn, sid, directory, archived=None, upd=None):
    conn.execute(
        "INSERT INTO session(id, directory, title, time_created, time_updated, time_archived)"
        " VALUES(?,?,?,?,?,?)",
        (sid, directory, f"title-{sid}", upd or now_ms(), upd or now_ms(), archived),
    )
    conn.commit()


def add_part(conn, sid, data, upd=None):
    conn.execute(
        "INSERT INTO part(id, session_id, time_updated, data) VALUES(?,?,?,?)",
        (f"p-{sid}-{len(data)}", sid, upd or now_ms(), json.dumps(data)),
    )
    conn.commit()


def test_pending_question_is_input(tmp_path):
    db, conn = make_db(tmp_path)
    add_session(conn, "s1", "/proj/a")
    add_part(conn, "s1", {"type": "tool", "tool": "question", "state": {"status": "pending"}})
    obs = DbObserver(db)
    snap = obs.snapshot_by_directory()
    assert "/proj/a" in snap
    assert snap["/proj/a"].has_pending_input
    assert len(snap["/proj/a"].pending_questions) == 1


def test_completed_question_is_not_input(tmp_path):
    db, conn = make_db(tmp_path)
    add_session(conn, "s1", "/proj/a")
    add_part(conn, "s1", {"type": "tool", "tool": "question", "state": {"status": "completed"}})
    obs = DbObserver(db)
    snap = obs.snapshot_by_directory()
    assert snap["/proj/a"].pending_questions == []


def test_errored_question_is_not_pending(tmp_path):
    # research section 6: "session.error -> do not invent a pending approval."
    db, conn = make_db(tmp_path)
    add_session(conn, "s1", "/proj/a")
    add_part(conn, "s1", {"type": "tool", "tool": "question", "state": {"status": "error"}})
    snap = DbObserver(db).snapshot_by_directory()
    assert snap["/proj/a"].pending_questions == []
    assert not snap["/proj/a"].has_pending_input


def test_recent_part_update_is_busy(tmp_path):
    db, conn = make_db(tmp_path)
    add_session(conn, "s1", "/proj/b")
    add_part(conn, "s1", {"type": "tool", "tool": "bash", "state": {"status": "running"}}, upd=now_ms())
    obs = DbObserver(db, run_window_ms=15000)
    snap = obs.snapshot_by_directory()
    assert snap["/proj/b"].status is Status.BUSY


def test_old_part_update_is_idle(tmp_path):
    db, conn = make_db(tmp_path)
    old = now_ms() - 120_000
    add_session(conn, "s1", "/proj/c", upd=old)
    add_part(conn, "s1", {"type": "text"}, upd=old)
    obs = DbObserver(db, run_window_ms=15000)
    snap = obs.snapshot_by_directory()
    assert snap["/proj/c"].status is Status.IDLE


def test_archived_session_excluded(tmp_path):
    db, conn = make_db(tmp_path)
    add_session(conn, "s1", "/proj/d", archived=now_ms())
    obs = DbObserver(db)
    snap = obs.snapshot_by_directory()
    assert "/proj/d" not in snap


def test_running_tool_stays_busy_without_fresh_parts(tmp_path):
    # research section 2: "Run a long tool without tokens -> Remains green."
    # A tool part still in state running/pending keeps the TUI busy even if no
    # part has updated within the recency window (a long command with no output).
    db, conn = make_db(tmp_path)
    add_session(conn, "s1", "/d/longtool")
    old = now_ms() - 60_000  # 60 s ago, well beyond the 15 s recency window
    add_part(conn, "s1", {"type": "tool", "tool": "bash", "state": {"status": "running"}}, upd=old)
    conn.close()
    st = DbObserver(db).snapshot_by_directory()["/d/longtool"]
    assert st.status is Status.BUSY


def test_missing_db_returns_empty(tmp_path):
    obs = DbObserver(tmp_path / "nope.db")
    assert obs.snapshot_by_directory() == {}


def test_pending_permission_is_input(tmp_path):
    db, conn = make_db(tmp_path)
    add_session(conn, "s1", "/proj/e")
    add_part(conn, "s1", {"type": "tool", "tool": "permission", "state": {"status": "asked"}})
    obs = DbObserver(db)
    snap = obs.snapshot_by_directory()
    assert len(snap["/proj/e"].pending_permissions) == 1


def test_observer_opens_db_read_only(tmp_path, monkeypatch):
    # the observer must not grab a write lock on OpenCode's live store
    db, conn = make_db(tmp_path)
    add_session(conn, "s1", "/d/a")
    conn.close()
    import opendeck_broker.opencode.observe as ob

    calls = []
    real_connect = sqlite3.connect

    def fake_connect(*a, **k):
        calls.append((a, k))
        return real_connect(*a, **k)

    monkeypatch.setattr(ob.sqlite3, "connect", fake_connect)
    obs = DbObserver(db)
    obs.snapshot_by_directory()
    assert len(calls) == 1
    args, kwargs = calls[0]
    assert kwargs.get("uri") is True
    assert args[0].startswith("file:")
    assert "mode=ro" in args[0]
