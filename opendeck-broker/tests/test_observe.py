import json
import sqlite3
import time
from pathlib import Path

from opendeck_broker.model import Status
from opendeck_broker.opencode.observe import DbObserver, default_db_path


def now_ms():
    return int(time.time() * 1000)


def test_has_pending_input_permissions_or_questions():
    # SessionState.has_pending_input is True for either pending permissions OR
    # pending questions (both are unresolved structured requests -> INPUT), and
    # False when neither is outstanding.
    from opendeck_broker.opencode.observe import SessionState

    assert SessionState(directory="/d", pending_permissions=["p1"]).has_pending_input
    assert SessionState(directory="/d", pending_questions=["q1"]).has_pending_input
    assert SessionState(directory="/d").has_pending_input is False


def test_norm_dir_normalizes_paths():
    # the observer/adapter key directories by a normalized path: None -> "",
    # backslashes -> forward slashes, trailing slash stripped.
    from opendeck_broker.opencode.observe import _norm_dir

    assert _norm_dir(None) == ""
    assert _norm_dir("") == ""
    assert _norm_dir("C:\\Users\\ryans\\proj") == "C:/Users/ryans/proj"
    assert _norm_dir("/d/a/") == "/d/a"
    assert _norm_dir("/d/a") == "/d/a"


def test_default_db_path_env_override_and_default(monkeypatch):
    # the observer must read the OpenCode global DB; OPENCODE_DB overrides the
    # default location, which is the standard OpenCode global path.
    monkeypatch.setenv("OPENCODE_DB", "/custom/path/oc.db")
    assert default_db_path() == Path("/custom/path/oc.db")
    monkeypatch.delenv("OPENCODE_DB", raising=False)
    p = default_db_path()
    assert p.name == "opencode.db"
    assert "opencode" in p.parts  # .../opencode/opencode.db


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


def test_child_session_pending_request_folds_into_parent_slot(tmp_path):
    # research: one TUI can own a subagent/child session in the same directory.
    # A child with a pending request must show INPUT on the parent's single
    # slot, not take a second slot.
    db, conn = make_db(tmp_path)
    add_session(conn, "parent", "/proj/shared")
    add_session(conn, "child", "/proj/shared")
    # only the child has a pending question
    add_part(conn, "child", {"type": "tool", "tool": "question", "state": {"status": "pending"}})
    obs = DbObserver(db)
    snap = obs.snapshot_by_directory()
    assert list(snap) == ["/proj/shared"]  # one slot, not two
    assert snap["/proj/shared"].has_pending_input
    assert len(snap["/proj/shared"].pending_questions) == 1


def test_multiple_pending_questions_are_all_counted(tmp_path):
    # a session with several unresolved question parts reports each one
    # (pending_questions grows with the count, not capped at one).
    db, conn = make_db(tmp_path)
    add_session(conn, "s1", "/proj/multi")
    for i in range(3):
        conn.execute(
            "INSERT INTO part(id, session_id, time_updated, data) VALUES(?,?,?,?)",
            (f"q-{i}", "s1", now_ms(),
             json.dumps({"type": "tool", "tool": "question", "state": {"status": "pending"}})),
        )
    conn.commit()
    st = DbObserver(db).snapshot_by_directory()["/proj/multi"]
    assert st.has_pending_input
    assert len(st.pending_questions) == 3


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


def test_default_run_window_is_15s(tmp_path):
    # the default recency window is 15 s (RUN_WINDOW_MS): a part ~10 s ago is
    # still "recent" (busy), a part ~20 s ago is not (idle, no active tool).
    from opendeck_broker.opencode.observe import RUN_WINDOW_MS

    assert RUN_WINDOW_MS == 15_000
    db, conn = make_db(tmp_path)
    add_session(conn, "s1", "/d/recent")
    add_part(conn, "s1", {"type": "text"}, upd=now_ms() - 10_000)
    add_session(conn, "s2", "/d/old")
    add_part(conn, "s2", {"type": "text"}, upd=now_ms() - 20_000)
    snap = DbObserver(db).snapshot_by_directory()  # default run window
    assert snap["/d/recent"].status is Status.BUSY
    assert snap["/d/old"].status is Status.IDLE


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


def test_pending_tool_stays_busy_without_fresh_parts(tmp_path):
    # the active_tool count includes both 'running' and 'pending': a queued tool
    # (not yet running) also keeps the TUI busy even without fresh parts.
    db, conn = make_db(tmp_path)
    add_session(conn, "s1", "/d/pendingtool")
    old = now_ms() - 60_000
    add_part(conn, "s1", {"type": "tool", "tool": "bash", "state": {"status": "pending"}}, upd=old)
    conn.close()
    st = DbObserver(db).snapshot_by_directory()["/d/pendingtool"]
    assert st.status is Status.BUSY


def test_completed_tool_is_not_active(tmp_path):
    # a tool that has completed (status not running/pending) is NOT active: with
    # no fresh parts the session reads idle.
    db, conn = make_db(tmp_path)
    add_session(conn, "s1", "/d/done")
    old = now_ms() - 60_000
    add_part(conn, "s1", {"type": "tool", "tool": "bash", "state": {"status": "completed"}}, upd=old)
    conn.close()
    st = DbObserver(db).snapshot_by_directory()["/d/done"]
    assert st.status is Status.IDLE


def test_session_with_no_parts_is_idle(tmp_path):
    # a live session with no parts (just launched, no activity yet) is idle --
    # no recent part update, no active tool, no pending requests.
    db, conn = make_db(tmp_path)
    add_session(conn, "s1", "/d/fresh")
    # no parts
    conn.close()
    st = DbObserver(db).snapshot_by_directory()["/d/fresh"]
    assert st.status is Status.IDLE
    assert not st.has_pending_input


def test_session_title_and_id_are_captured(tmp_path):
    # the observer captures the session title and id (for diagnostics / the
    # display identity), alongside the directory-keyed state facts.
    db, conn = make_db(tmp_path)
    add_session(conn, "s1", "/d/titled")
    st = DbObserver(db).snapshot_by_directory()["/d/titled"]
    assert st.session_id == "s1"
    assert st.title == "title-s1"  # the add_session helper's title
    assert st.has_session is True


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


def test_both_pending_permission_and_question_are_input(tmp_path):
    # a session with BOTH a pending permission and a pending question at the same
    # time is still INPUT; both request kinds are captured (not one shadowing the
    # other).
    db, conn = make_db(tmp_path)
    add_session(conn, "s1", "/proj/both")
    # explicit distinct part ids (the add_part helper derives its id from
    # len(data), which collides for two same-shape dicts)
    conn.execute("INSERT INTO part(id, session_id, time_updated, data) VALUES(?,?,?,?)",
                 ("part-perm", "s1", now_ms(),
                  json.dumps({"type": "tool", "tool": "permission", "state": {"status": "asked"}})))
    conn.execute("INSERT INTO part(id, session_id, time_updated, data) VALUES(?,?,?,?)",
                 ("part-quest", "s1", now_ms(),
                  json.dumps({"type": "tool", "tool": "question", "state": {"status": "pending"}})))
    conn.commit()
    st = DbObserver(db).snapshot_by_directory()["/proj/both"]
    assert st.has_pending_input
    assert len(st.pending_permissions) == 1
    assert len(st.pending_questions) == 1


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
