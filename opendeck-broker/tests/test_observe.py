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


def test_running_question_is_pending(tmp_path):
    # a question part whose status is "running" (not in the resolved set
    # completed/error/replied/rejected) is still an unresolved structured request
    # -> counted as pending (INPUT).
    db, conn = make_db(tmp_path)
    add_session(conn, "s1", "/d/runq")
    add_part(conn, "s1", {"type": "tool", "tool": "question", "state": {"status": "running"}})
    st = DbObserver(db).snapshot_by_directory()["/d/runq"]
    assert st.has_pending_input
    assert len(st.pending_questions) == 1


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


def test_two_sessions_fold_question_and_permission_into_one_slot(tmp_path):
    # two live sessions in one directory, each with a *different* pending request
    # kind (one a question, one a permission): both fold into the single slot for
    # that directory -- the slot reports has_pending_input True with one question
    # AND one permission, not two slots. The per-kind pending tallies are folded
    # across sessions independently of each other.
    db, conn = make_db(tmp_path)
    add_session(conn, "s-q", "/proj/two")
    add_session(conn, "s-p", "/proj/two")
    add_part(conn, "s-q", {"type": "tool", "tool": "question", "state": {"status": "pending"}})
    add_part(conn, "s-p", {"type": "tool", "tool": "permission", "state": {"status": "pending"}})
    snap = DbObserver(db).snapshot_by_directory()
    assert list(snap) == ["/proj/two"]  # one slot, not two
    st = snap["/proj/two"]
    assert st.has_pending_input
    assert len(st.pending_questions) == 1
    assert len(st.pending_permissions) == 1


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


def test_rejected_question_is_not_pending(tmp_path):
    # a question part whose status is "rejected" (a resolved status) is not
    # counted as pending -- completing the resolved-question status coverage.
    db, conn = make_db(tmp_path)
    add_session(conn, "s1", "/d/rejectedq")
    add_part(conn, "s1", {"type": "tool", "tool": "question", "state": {"status": "rejected"}})
    st = DbObserver(db).snapshot_by_directory()["/d/rejectedq"]
    assert st.pending_questions == []
    assert not st.has_pending_input


def test_completed_question_is_not_input(tmp_path):
    db, conn = make_db(tmp_path)
    add_session(conn, "s1", "/proj/a")
    add_part(conn, "s1", {"type": "tool", "tool": "question", "state": {"status": "completed"}})
    obs = DbObserver(db)
    snap = obs.snapshot_by_directory()
    assert snap["/proj/a"].pending_questions == []


def test_replied_question_is_not_pending(tmp_path):
    # a question part whose status is "replied" (a resolved status) is not
    # counted as pending -- parallel to the completed/error cases for questions.
    db, conn = make_db(tmp_path)
    add_session(conn, "s1", "/d/repliedq")
    add_part(conn, "s1", {"type": "tool", "tool": "question", "state": {"status": "replied"}})
    st = DbObserver(db).snapshot_by_directory()["/d/repliedq"]
    assert st.pending_questions == []
    assert not st.has_pending_input


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


def test_recent_part_update_with_completed_tool_is_busy(tmp_path):
    # recency drives busy, not the tool status: a part updated within the window
    # keeps the TUI busy even if the last tool has completed (fresh activity).
    db, conn = make_db(tmp_path)
    add_session(conn, "s1", "/d/recentdone")
    add_part(conn, "s1", {"type": "tool", "tool": "bash", "state": {"status": "completed"}}, upd=now_ms() - 2_000)
    st = DbObserver(db).snapshot_by_directory()["/d/recentdone"]
    assert st.status is Status.BUSY


def test_old_part_update_is_idle(tmp_path):
    db, conn = make_db(tmp_path)
    old = now_ms() - 120_000
    add_session(conn, "s1", "/proj/c", upd=old)
    add_part(conn, "s1", {"type": "text"}, upd=old)
    obs = DbObserver(db, run_window_ms=15000)
    snap = obs.snapshot_by_directory()
    assert snap["/proj/c"].status is Status.IDLE


def test_multi_session_same_dir_latest_recency_drives_busy(tmp_path):
    # two live sessions in the same directory share one slot: the directory's
    # busy state is driven by the MOST RECENT part update across both (a fresh
    # update in either one keeps the slot busy), while pending requests fold.
    db, conn = make_db(tmp_path)
    add_session(conn, "old", "/d/shared", upd=now_ms() - 120_000)
    add_part(conn, "old", {"type": "text"}, upd=now_ms() - 120_000)
    add_session(conn, "new", "/d/shared")
    add_part(conn, "new", {"type": "text"}, upd=now_ms() - 3_000)  # recent in one
    st = DbObserver(db).snapshot_by_directory()["/d/shared"]
    assert st.status is Status.BUSY  # the recent update drives busy


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


def test_session_with_null_directory_is_keyed_to_empty(tmp_path):
    # a session whose directory is NULL is keyed to the normalized empty string
    # (the observer/adapter key directories by _norm_dir, which maps None -> "").
    db, conn = make_db(tmp_path)
    conn.execute(
        "INSERT INTO session(id, directory, title, time_created, time_updated, time_archived)"
        " VALUES(?,?,?,?,?,?)",
        ("s-null", None, "title", now_ms(), now_ms(), None),
    )
    conn.commit()
    snap = DbObserver(db).snapshot_by_directory()
    assert "" in snap  # the null directory is keyed to ""
    assert snap[""].has_session


def test_observer_normalizes_windows_drive_path_end_to_end(tmp_path):
    # a session whose directory is a Windows drive path with backslashes
    # (C:\\Users\\ryans\\proj\\) is keyed to the normalized forward-slash form
    # (C:/Users/ryans/proj) end-to-end through the DB -- the observer applies
    # _norm_dir to the raw directory value before keying. This is the real-world
    # case on the target host: OpenCode stores the launch directory with Windows
    # separators, and the deck must key slots by the canonical form.
    db, conn = make_db(tmp_path)
    add_session(conn, "s1", "C:\\Users\\ryans\\proj\\")
    add_part(conn, "s1", {"type": "tool", "tool": "bash", "state": {"status": "running"}})
    snap = DbObserver(db).snapshot_by_directory()
    # the raw backslash path is NOT the key; the normalized forward-slash path is.
    assert "C:\\Users\\ryans\\proj\\" not in snap
    assert "C:/Users/ryans/proj" in snap
    st = snap["C:/Users/ryans/proj"]
    assert st.has_session
    assert st.status is Status.BUSY


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


def test_part_with_invalid_json_degrades_the_reader(tmp_path):
    # a part whose data is not valid JSON makes json_extract raise (malformed
    # JSON), so the whole read degrades (the adapter catches it -> UNKNOWN)
    # rather than silently returning a partial, wrong count.
    db, conn = make_db(tmp_path)
    add_session(conn, "s1", "/d/badjson")
    old = now_ms() - 120_000
    conn.execute(
        "INSERT INTO part(id, session_id, time_updated, data) VALUES(?,?,?,?)",
        ("p-bad", "s1", old, "not json at all"),
    )
    conn.commit()
    import pytest as _pt

    with _pt.raises(Exception):
        DbObserver(db).snapshot_by_directory()


def test_missing_db_returns_empty(tmp_path):
    obs = DbObserver(tmp_path / "nope.db")
    assert obs.snapshot_by_directory() == {}


def test_pending_status_permission_is_pending(tmp_path):
    # a permission part whose status is "pending" (a non-resolved status, not in
    # the resolved set) is counted as pending (INPUT) -- parallel to "asked".
    db, conn = make_db(tmp_path)
    add_session(conn, "s1", "/d/pendingperm")
    conn.execute(
        "INSERT INTO part(id, session_id, time_updated, data) VALUES(?,?,?,?)",
        ("p-pend", "s1", now_ms(),
         json.dumps({"type": "tool", "tool": "permission", "state": {"status": "pending"}})),
    )
    conn.commit()
    st = DbObserver(db).snapshot_by_directory()["/d/pendingperm"]
    assert st.has_pending_input
    assert len(st.pending_permissions) == 1


def test_running_permission_is_pending(tmp_path):
    # a permission part whose status is "running" (not in the resolved set) is
    # still an unresolved structured request -> pending (INPUT); parallel to the
    # running-question case.
    db, conn = make_db(tmp_path)
    add_session(conn, "s1", "/d/runperm")
    conn.execute(
        "INSERT INTO part(id, session_id, time_updated, data) VALUES(?,?,?,?)",
        ("p-run", "s1", now_ms(),
         json.dumps({"type": "tool", "tool": "permission", "state": {"status": "running"}})),
    )
    conn.commit()
    st = DbObserver(db).snapshot_by_directory()["/d/runperm"]
    assert st.has_pending_input
    assert len(st.pending_permissions) == 1


def test_replied_permission_is_not_pending(tmp_path):
    # a permission part whose status is "replied" (one of the resolved statuses)
    # is not counted as pending -- only unresolved ones (asked/pending) are INPUT.
    db, conn = make_db(tmp_path)
    add_session(conn, "s1", "/d/replied")
    conn.execute(
        "INSERT INTO part(id, session_id, time_updated, data) VALUES(?,?,?,?)",
        ("p-rep", "s1", now_ms(),
         json.dumps({"type": "tool", "tool": "permission", "state": {"status": "replied"}})),
    )
    conn.commit()
    st = DbObserver(db).snapshot_by_directory()["/d/replied"]
    assert st.pending_permissions == []
    assert not st.has_pending_input


def test_rejected_permission_is_not_pending(tmp_path):
    # a permission part whose status is "rejected" (a resolved status) is not
    # counted as pending -- parallel to the "replied"/"completed"/"error" cases.
    db, conn = make_db(tmp_path)
    add_session(conn, "s1", "/d/rejected")
    conn.execute(
        "INSERT INTO part(id, session_id, time_updated, data) VALUES(?,?,?,?)",
        ("p-rej", "s1", now_ms(),
         json.dumps({"type": "tool", "tool": "permission", "state": {"status": "rejected"}})),
    )
    conn.commit()
    st = DbObserver(db).snapshot_by_directory()["/d/rejected"]
    assert st.pending_permissions == []
    assert not st.has_pending_input


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


def test_mixed_pending_question_and_resolved_permission(tmp_path):
    # a session with a pending question AND an already-replied permission: the
    # pending question drives INPUT (has_pending_input True, 1 pending question),
    # while the replied permission is NOT counted (pending_permissions empty).
    # The two request kinds are tallied independently.
    db, conn = make_db(tmp_path)
    add_session(conn, "s1", "/d/mixed")
    conn.execute("INSERT INTO part(id, session_id, time_updated, data) VALUES(?,?,?,?)",
                 ("part-rep", "s1", now_ms(),
                  json.dumps({"type": "tool", "tool": "permission", "state": {"status": "replied"}})))
    conn.execute("INSERT INTO part(id, session_id, time_updated, data) VALUES(?,?,?,?)",
                 ("part-quest", "s1", now_ms(),
                  json.dumps({"type": "tool", "tool": "question", "state": {"status": "pending"}})))
    conn.commit()
    st = DbObserver(db).snapshot_by_directory()["/d/mixed"]
    assert st.has_pending_input
    assert len(st.pending_questions) == 1
    assert st.pending_permissions == []


def test_running_tool_with_both_pending_requests(tmp_path):
    # a session with a running tool AND a pending permission AND a pending
    # question: the status is BUSY (the running tool), has_pending_input True,
    # and BOTH pending requests are captured independently (1 permission, 1
    # question). The reducer would show INPUT (pending beats busy).
    db, conn = make_db(tmp_path)
    add_session(conn, "s1", "/d/all")
    conn.execute("INSERT INTO part(id, session_id, time_updated, data) VALUES(?,?,?,?)",
                 ("part-tool", "s1", now_ms(),
                  json.dumps({"type": "tool", "tool": "bash", "state": {"status": "running"}})))
    conn.execute("INSERT INTO part(id, session_id, time_updated, data) VALUES(?,?,?,?)",
                 ("part-perm", "s1", now_ms(),
                  json.dumps({"type": "tool", "tool": "permission", "state": {"status": "asked"}})))
    conn.execute("INSERT INTO part(id, session_id, time_updated, data) VALUES(?,?,?,?)",
                 ("part-quest", "s1", now_ms(),
                  json.dumps({"type": "tool", "tool": "question", "state": {"status": "pending"}})))
    conn.commit()
    st = DbObserver(db).snapshot_by_directory()["/d/all"]
    assert st.status is Status.BUSY
    assert st.has_pending_input
    assert len(st.pending_permissions) == 1
    assert len(st.pending_questions) == 1


def test_mixed_pending_and_resolved_questions(tmp_path):
    # a session with a pending question AND an already-completed question: the
    # pending question drives INPUT (has_pending_input True) and is the only one
    # counted (pending_questions has 1 entry, not 2) -- resolved questions are
    # excluded from the pending tally.
    db, conn = make_db(tmp_path)
    add_session(conn, "s1", "/d/mq")
    conn.execute("INSERT INTO part(id, session_id, time_updated, data) VALUES(?,?,?,?)",
                 ("part-pend", "s1", now_ms(),
                  json.dumps({"type": "tool", "tool": "question", "state": {"status": "pending"}})))
    conn.execute("INSERT INTO part(id, session_id, time_updated, data) VALUES(?,?,?,?)",
                 ("part-done", "s1", now_ms(),
                  json.dumps({"type": "tool", "tool": "question", "state": {"status": "completed"}})))
    conn.commit()
    st = DbObserver(db).snapshot_by_directory()["/d/mq"]
    assert st.has_pending_input
    assert len(st.pending_questions) == 1  # only the pending one, not the completed one


def test_running_tool_with_resolved_question_and_permission(tmp_path):
    # a session with a running tool AND a completed question AND a replied
    # permission: the running tool drives BUSY (green), and BOTH resolved requests
    # are excluded from the pending tally -- has_pending_input is False, so the
    # status is BUSY, not INPUT. The resolved-status filter works for both kinds.
    db, conn = make_db(tmp_path)
    add_session(conn, "s1", "/d/resolved")
    conn.execute("INSERT INTO part(id, session_id, time_updated, data) VALUES(?,?,?,?)",
                 ("p-tool", "s1", now_ms(),
                  json.dumps({"type": "tool", "tool": "bash", "state": {"status": "running"}})))
    conn.execute("INSERT INTO part(id, session_id, time_updated, data) VALUES(?,?,?,?)",
                 ("p-quest", "s1", now_ms(),
                  json.dumps({"type": "tool", "tool": "question", "state": {"status": "completed"}})))
    conn.execute("INSERT INTO part(id, session_id, time_updated, data) VALUES(?,?,?,?)",
                 ("p-perm", "s1", now_ms(),
                  json.dumps({"type": "tool", "tool": "permission", "state": {"status": "replied"}})))
    conn.commit()
    st = DbObserver(db).snapshot_by_directory()["/d/resolved"]
    assert st.status is Status.BUSY
    assert st.has_pending_input is False
    assert st.pending_questions == []
    assert st.pending_permissions == []


def test_running_tool_with_completed_question(tmp_path):
    # a session with a running tool AND a completed question: the running tool
    # drives BUSY (green) and the completed question is NOT pending (the question
    # was answered), so has_pending_input is False -- the status is BUSY, not INPUT.
    db, conn = make_db(tmp_path)
    add_session(conn, "s1", "/d/rt")
    conn.execute("INSERT INTO part(id, session_id, time_updated, data) VALUES(?,?,?,?)",
                 ("p-tool", "s1", now_ms(),
                  json.dumps({"type": "tool", "tool": "bash", "state": {"status": "running"}})))
    conn.execute("INSERT INTO part(id, session_id, time_updated, data) VALUES(?,?,?,?)",
                 ("p-quest", "s1", now_ms(),
                  json.dumps({"type": "tool", "tool": "question", "state": {"status": "completed"}})))
    conn.commit()
    st = DbObserver(db).snapshot_by_directory()["/d/rt"]
    assert st.status is Status.BUSY
    assert st.has_pending_input is False


def test_running_tool_with_running_question_is_busy_and_input(tmp_path):
    # a session with a running tool AND a question whose status is "running" (not
    # in the resolved set): the running tool drives BUSY, and the running question
    # is still an unresolved request, so has_pending_input is True. The reducer
    # would show INPUT (pending beats busy). This is the "tool is mid-flight and
    # the model is simultaneously asking a structured question" case.
    db, conn = make_db(tmp_path)
    add_session(conn, "s1", "/d/runq2")
    conn.execute("INSERT INTO part(id, session_id, time_updated, data) VALUES(?,?,?,?)",
                 ("p-tool", "s1", now_ms(),
                  json.dumps({"type": "tool", "tool": "bash", "state": {"status": "running"}})))
    conn.execute("INSERT INTO part(id, session_id, time_updated, data) VALUES(?,?,?,?)",
                 ("p-quest", "s1", now_ms(),
                  json.dumps({"type": "tool", "tool": "question", "state": {"status": "running"}})))
    conn.commit()
    st = DbObserver(db).snapshot_by_directory()["/d/runq2"]
    assert st.status is Status.BUSY
    assert st.has_pending_input is True
    assert len(st.pending_questions) == 1


def test_running_tool_with_running_permission_is_busy_and_input(tmp_path):
    # a session with a running tool AND a permission whose status is "running" (not
    # in the resolved set): the running tool drives BUSY, and the running permission
    # is still an unresolved request, so has_pending_input is True. The reducer
    # would show INPUT (pending beats busy). The mirror of the running-question case
    # for the other request kind.
    db, conn = make_db(tmp_path)
    add_session(conn, "s1", "/d/runp")
    conn.execute("INSERT INTO part(id, session_id, time_updated, data) VALUES(?,?,?,?)",
                 ("p-tool", "s1", now_ms(),
                  json.dumps({"type": "tool", "tool": "bash", "state": {"status": "running"}})))
    conn.execute("INSERT INTO part(id, session_id, time_updated, data) VALUES(?,?,?,?)",
                 ("p-perm", "s1", now_ms(),
                  json.dumps({"type": "tool", "tool": "permission", "state": {"status": "running"}})))
    conn.commit()
    st = DbObserver(db).snapshot_by_directory()["/d/runp"]
    assert st.status is Status.BUSY
    assert st.has_pending_input is True
    assert len(st.pending_permissions) == 1


def test_running_tool_with_mixed_resolved_and_pending_requests(tmp_path):
    # a session with a running tool AND a pending question AND a replied
    # permission AND a rejected question: the running tool drives BUSY, the
    # pending question is unresolved (has_pending_input True, 1 pending question),
    # while BOTH the replied permission and the rejected question are resolved
    # (pending_permissions empty, the second question not counted). The per-kind,
    # per-status resolved filter works for a realistic mix of request parts.
    db, conn = make_db(tmp_path)
    add_session(conn, "s1", "/d/mix2")
    conn.execute("INSERT INTO part(id, session_id, time_updated, data) VALUES(?,?,?,?)",
                 ("p-tool", "s1", now_ms(),
                  json.dumps({"type": "tool", "tool": "bash", "state": {"status": "running"}})))
    conn.execute("INSERT INTO part(id, session_id, time_updated, data) VALUES(?,?,?,?)",
                 ("p-quest-pending", "s1", now_ms(),
                  json.dumps({"type": "tool", "tool": "question", "state": {"status": "pending"}})))
    conn.execute("INSERT INTO part(id, session_id, time_updated, data) VALUES(?,?,?,?)",
                 ("p-perm-replied", "s1", now_ms(),
                  json.dumps({"type": "tool", "tool": "permission", "state": {"status": "replied"}})))
    conn.execute("INSERT INTO part(id, session_id, time_updated, data) VALUES(?,?,?,?)",
                 ("p-quest-rejected", "s1", now_ms(),
                  json.dumps({"type": "tool", "tool": "question", "state": {"status": "rejected"}})))
    conn.commit()
    st = DbObserver(db).snapshot_by_directory()["/d/mix2"]
    assert st.status is Status.BUSY
    assert st.has_pending_input is True
    assert len(st.pending_questions) == 1  # only the pending one; rejected excluded
    assert st.pending_permissions == []  # replied permission is resolved


def test_running_tool_with_multiple_resolved_statuses_excluded(tmp_path):
    # a session with a running tool AND one pending question AND one pending
    # permission AND one replied question AND one error permission: the running
    # tool drives BUSY, the pending question and permission are unresolved
    # (has_pending_input True, 1 each), while BOTH the replied question and the
    # error permission are resolved (not counted). Exercises the full resolved
    # status set (replied for questions, error for permissions) alongside the
    # pending ones in one snapshot.
    db, conn = make_db(tmp_path)
    add_session(conn, "s1", "/d/mix3")
    conn.execute("INSERT INTO part(id, session_id, time_updated, data) VALUES(?,?,?,?)",
                 ("p-tool", "s1", now_ms(),
                  json.dumps({"type": "tool", "tool": "bash", "state": {"status": "running"}})))
    conn.execute("INSERT INTO part(id, session_id, time_updated, data) VALUES(?,?,?,?)",
                 ("p-q-pending", "s1", now_ms(),
                  json.dumps({"type": "tool", "tool": "question", "state": {"status": "pending"}})))
    conn.execute("INSERT INTO part(id, session_id, time_updated, data) VALUES(?,?,?,?)",
                 ("p-p-pending", "s1", now_ms(),
                  json.dumps({"type": "tool", "tool": "permission", "state": {"status": "pending"}})))
    conn.execute("INSERT INTO part(id, session_id, time_updated, data) VALUES(?,?,?,?)",
                 ("p-q-replied", "s1", now_ms(),
                  json.dumps({"type": "tool", "tool": "question", "state": {"status": "replied"}})))
    conn.execute("INSERT INTO part(id, session_id, time_updated, data) VALUES(?,?,?,?)",
                 ("p-p-error", "s1", now_ms(),
                  json.dumps({"type": "tool", "tool": "permission", "state": {"status": "error"}})))
    conn.commit()
    st = DbObserver(db).snapshot_by_directory()["/d/mix3"]
    assert st.status is Status.BUSY
    assert st.has_pending_input is True
    assert len(st.pending_questions) == 1  # only the pending question; replied excluded
    assert len(st.pending_permissions) == 1  # only the pending permission; error excluded


def test_running_tool_with_two_pending_questions_counts_both(tmp_path):
    # a session with a running tool AND two pending questions (a realistic
    # "model asked follow-up A, then follow-up B" situation): the running tool
    # drives BUSY, and BOTH pending questions are counted independently
    # (has_pending_input True, pending_questions length 2). The per-kind tally is
    # a COUNT, not a boolean -- the reducer shows INPUT either way, but the count
    # is what the diagnostics/observer expose for a multi-pending TUI.
    db, conn = make_db(tmp_path)
    add_session(conn, "s1", "/d/twopq")
    conn.execute("INSERT INTO part(id, session_id, time_updated, data) VALUES(?,?,?,?)",
                 ("p-tool", "s1", now_ms(),
                  json.dumps({"type": "tool", "tool": "bash", "state": {"status": "running"}})))
    conn.execute("INSERT INTO part(id, session_id, time_updated, data) VALUES(?,?,?,?)",
                 ("p-q1", "s1", now_ms(),
                  json.dumps({"type": "tool", "tool": "question", "state": {"status": "pending"}})))
    conn.execute("INSERT INTO part(id, session_id, time_updated, data) VALUES(?,?,?,?)",
                 ("p-q2", "s1", now_ms(),
                  json.dumps({"type": "tool", "tool": "question", "state": {"status": "pending"}})))
    conn.commit()
    st = DbObserver(db).snapshot_by_directory()["/d/twopq"]
    assert st.status is Status.BUSY
    assert st.has_pending_input is True
    assert len(st.pending_questions) == 2
    assert st.pending_permissions == []


def test_running_tool_with_two_pending_each_kind_counts_all(tmp_path):
    # a session with a running tool AND two pending questions AND two pending
    # permissions (a heavily-interacting TUI): the running tool drives BUSY, and
    # BOTH kinds are counted independently (has_pending_input True, 2 pending
    # questions AND 2 pending permissions). The two per-kind tallies are computed
    # in separate SQL subqueries and never cross-contaminate, even at higher
    # counts.
    db, conn = make_db(tmp_path)
    add_session(conn, "s1", "/d/twoboth")
    conn.execute("INSERT INTO part(id, session_id, time_updated, data) VALUES(?,?,?,?)",
                 ("p-tool", "s1", now_ms(),
                  json.dumps({"type": "tool", "tool": "bash", "state": {"status": "running"}})))
    for i in (1, 2):
        conn.execute("INSERT INTO part(id, session_id, time_updated, data) VALUES(?,?,?,?)",
                     (f"p-q{i}", "s1", now_ms(),
                      json.dumps({"type": "tool", "tool": "question", "state": {"status": "pending"}})))
    for i in (1, 2):
        conn.execute("INSERT INTO part(id, session_id, time_updated, data) VALUES(?,?,?,?)",
                     (f"p-p{i}", "s1", now_ms(),
                      json.dumps({"type": "tool", "tool": "permission", "state": {"status": "pending"}})))
    conn.commit()
    st = DbObserver(db).snapshot_by_directory()["/d/twoboth"]
    assert st.status is Status.BUSY
    assert st.has_pending_input is True
    assert len(st.pending_questions) == 2
    assert len(st.pending_permissions) == 2


def test_running_tool_with_pending_question_and_running_permission(tmp_path):
    # a session with a running tool AND a pending question AND a running
    # permission (the permission is mid-flight, not yet replied): the running
    # tool drives BUSY, and BOTH requests are unresolved -- the pending question
    # (status pending) and the running permission (status running, not in the
    # resolved set) -- so has_pending_input True with 1 pending question and 1
    # pending permission. Exercises a non-"pending" status (running) on the
    # permission side alongside a "pending" status on the question side.
    db, conn = make_db(tmp_path)
    add_session(conn, "s1", "/d/mixedstatus")
    conn.execute("INSERT INTO part(id, session_id, time_updated, data) VALUES(?,?,?,?)",
                 ("p-tool", "s1", now_ms(),
                  json.dumps({"type": "tool", "tool": "bash", "state": {"status": "running"}})))
    conn.execute("INSERT INTO part(id, session_id, time_updated, data) VALUES(?,?,?,?)",
                 ("p-q", "s1", now_ms(),
                  json.dumps({"type": "tool", "tool": "question", "state": {"status": "pending"}})))
    conn.execute("INSERT INTO part(id, session_id, time_updated, data) VALUES(?,?,?,?)",
                 ("p-p", "s1", now_ms(),
                  json.dumps({"type": "tool", "tool": "permission", "state": {"status": "running"}})))
    conn.commit()
    st = DbObserver(db).snapshot_by_directory()["/d/mixedstatus"]
    assert st.status is Status.BUSY
    assert st.has_pending_input is True
    assert len(st.pending_questions) == 1
    assert len(st.pending_permissions) == 1


def test_running_tool_with_pending_and_running_question_plus_running_permission(tmp_path):
    # a session with a running tool AND a pending question AND a running question
    # AND a running permission: BOTH question parts are unresolved (one pending,
    # one running -- neither in the resolved set) so pending_questions is 2, and
    # the running permission is unresolved so pending_permissions is 1. The
    # running tool drives BUSY. This exercises the full non-resolved status space
    # (pending + running) across both request kinds simultaneously.
    db, conn = make_db(tmp_path)
    add_session(conn, "s1", "/d/mixed2")
    conn.execute("INSERT INTO part(id, session_id, time_updated, data) VALUES(?,?,?,?)",
                 ("p-tool", "s1", now_ms(),
                  json.dumps({"type": "tool", "tool": "bash", "state": {"status": "running"}})))
    conn.execute("INSERT INTO part(id, session_id, time_updated, data) VALUES(?,?,?,?)",
                 ("p-q-pending", "s1", now_ms(),
                  json.dumps({"type": "tool", "tool": "question", "state": {"status": "pending"}})))
    conn.execute("INSERT INTO part(id, session_id, time_updated, data) VALUES(?,?,?,?)",
                 ("p-q-running", "s1", now_ms(),
                  json.dumps({"type": "tool", "tool": "question", "state": {"status": "running"}})))
    conn.execute("INSERT INTO part(id, session_id, time_updated, data) VALUES(?,?,?,?)",
                 ("p-p-running", "s1", now_ms(),
                  json.dumps({"type": "tool", "tool": "permission", "state": {"status": "running"}})))
    conn.commit()
    st = DbObserver(db).snapshot_by_directory()["/d/mixed2"]
    assert st.status is Status.BUSY
    assert st.has_pending_input is True
    assert len(st.pending_questions) == 2  # pending + running, both unresolved
    assert len(st.pending_permissions) == 1  # running permission, unresolved


def test_running_tool_with_full_non_resolved_matrix_counts_each_kind(tmp_path):
    # a session with a running tool AND every non-resolved status of both request
    # kinds (a pending question, a running question, a pending permission, a
    # running permission): all four are unresolved, so the observer reports 2
    # pending questions AND 2 pending permissions, and the running tool drives
    # BUSY. This is the full non-resolved status matrix (pending x running) for
    # both kinds in one snapshot -- the strongest assertion that the per-kind,
    # per-status filter is correct.
    db, conn = make_db(tmp_path)
    add_session(conn, "s1", "/d/fullmatrix")
    conn.execute("INSERT INTO part(id, session_id, time_updated, data) VALUES(?,?,?,?)",
                 ("p-tool", "s1", now_ms(),
                  json.dumps({"type": "tool", "tool": "bash", "state": {"status": "running"}})))
    for qid, qstatus in (("p-q-p", "pending"), ("p-q-r", "running")):
        conn.execute("INSERT INTO part(id, session_id, time_updated, data) VALUES(?,?,?,?)",
                     (qid, "s1", now_ms(),
                      json.dumps({"type": "tool", "tool": "question", "state": {"status": qstatus}})))
    for pid, pstatus in (("p-p-p", "pending"), ("p-p-r", "running")):
        conn.execute("INSERT INTO part(id, session_id, time_updated, data) VALUES(?,?,?,?)",
                     (pid, "s1", now_ms(),
                      json.dumps({"type": "tool", "tool": "permission", "state": {"status": pstatus}})))
    conn.commit()
    st = DbObserver(db).snapshot_by_directory()["/d/fullmatrix"]
    assert st.status is Status.BUSY
    assert st.has_pending_input is True
    assert len(st.pending_questions) == 2  # pending + running
    assert len(st.pending_permissions) == 2  # pending + running


def test_running_tool_with_full_matrix_plus_resolved_excluded(tmp_path):
    # a session with a running tool AND the full non-resolved matrix (pending +
    # running for both kinds) AND one resolved question (replied) AND one resolved
    # permission (rejected): the running tool drives BUSY, the four non-resolved
    # requests are counted (2 pending questions AND 2 pending permissions), and
    # BOTH the replied question and the rejected permission are excluded. This is
    # the complete status space (all 6 distinct statuses across both kinds) in a
    # single snapshot -- the strongest single assertion that the per-kind,
    # per-status filter partitions correctly.
    db, conn = make_db(tmp_path)
    add_session(conn, "s1", "/d/fullplus")
    conn.execute("INSERT INTO part(id, session_id, time_updated, data) VALUES(?,?,?,?)",
                 ("p-tool", "s1", now_ms(),
                  json.dumps({"type": "tool", "tool": "bash", "state": {"status": "running"}})))
    for qid, qstatus in (("p-q-p", "pending"), ("p-q-r", "running"), ("p-q-replied", "replied")):
        conn.execute("INSERT INTO part(id, session_id, time_updated, data) VALUES(?,?,?,?)",
                     (qid, "s1", now_ms(),
                      json.dumps({"type": "tool", "tool": "question", "state": {"status": qstatus}})))
    for pid, pstatus in (("p-p-p", "pending"), ("p-p-r", "running"), ("p-p-rejected", "rejected")):
        conn.execute("INSERT INTO part(id, session_id, time_updated, data) VALUES(?,?,?,?)",
                     (pid, "s1", now_ms(),
                      json.dumps({"type": "tool", "tool": "permission", "state": {"status": pstatus}})))
    conn.commit()
    st = DbObserver(db).snapshot_by_directory()["/d/fullplus"]
    assert st.status is Status.BUSY
    assert st.has_pending_input is True
    assert len(st.pending_questions) == 2  # pending + running; replied excluded
    assert len(st.pending_permissions) == 2  # pending + running; rejected excluded


def test_running_tool_with_exhaustive_status_partition(tmp_path):
    # a session with a running tool AND a pending question AND a pending
    # permission AND EVERY resolved status of both kinds (completed question,
    # replied question, error question, replied permission, rejected permission,
    # error permission): the running tool drives BUSY, the two pending requests
    # are counted (1 pending question, 1 pending permission), and ALL SIX
    # resolved requests are excluded. This exhausts the full status partition --
    # pending/running (non-resolved) vs completed/replied/rejected/error
    # (resolved) -- across both request kinds in one snapshot.
    db, conn = make_db(tmp_path)
    add_session(conn, "s1", "/d/exhaustive")
    conn.execute("INSERT INTO part(id, session_id, time_updated, data) VALUES(?,?,?,?)",
                 ("p-tool", "s1", now_ms(),
                  json.dumps({"type": "tool", "tool": "bash", "state": {"status": "running"}})))
    conn.execute("INSERT INTO part(id, session_id, time_updated, data) VALUES(?,?,?,?)",
                 ("p-q-pending", "s1", now_ms(),
                  json.dumps({"type": "tool", "tool": "question", "state": {"status": "pending"}})))
    conn.execute("INSERT INTO part(id, session_id, time_updated, data) VALUES(?,?,?,?)",
                 ("p-p-pending", "s1", now_ms(),
                  json.dumps({"type": "tool", "tool": "permission", "state": {"status": "pending"}})))
    # every resolved status of both kinds
    for qid, qstatus in (("p-q-completed", "completed"), ("p-q-replied", "replied"), ("p-q-error", "error")):
        conn.execute("INSERT INTO part(id, session_id, time_updated, data) VALUES(?,?,?,?)",
                     (qid, "s1", now_ms(),
                      json.dumps({"type": "tool", "tool": "question", "state": {"status": qstatus}})))
    for pid, pstatus in (("p-p-replied", "replied"), ("p-p-rejected", "rejected"), ("p-p-error", "error")):
        conn.execute("INSERT INTO part(id, session_id, time_updated, data) VALUES(?,?,?,?)",
                     (pid, "s1", now_ms(),
                      json.dumps({"type": "tool", "tool": "permission", "state": {"status": pstatus}})))
    conn.commit()
    st = DbObserver(db).snapshot_by_directory()["/d/exhaustive"]
    assert st.status is Status.BUSY
    assert st.has_pending_input is True
    assert len(st.pending_questions) == 1  # only the pending one; 3 resolved excluded
    assert len(st.pending_permissions) == 1  # only the pending one; 3 resolved excluded


def test_running_tool_with_full_status_space_counts_only_non_resolved(tmp_path):
    # a session with a running tool AND the FULL status space of both request
    # kinds (pending, running for both; AND every resolved status: completed,
    # replied, error for questions, and replied, rejected, error for
    # permissions): the running tool drives BUSY, the four non-resolved requests
    # are counted (2 pending questions, 2 pending permissions), and ALL SIX
    # resolved requests are excluded. This is the complete status space (all 8
    # distinct statuses) in one snapshot -- the strongest possible single
    # assertion that the per-kind, per-status filter partitions every status
    # exactly once into either the pending tally or the resolved exclusion.
    db, conn = make_db(tmp_path)
    add_session(conn, "s1", "/d/fullspace")
    conn.execute("INSERT INTO part(id, session_id, time_updated, data) VALUES(?,?,?,?)",
                 ("p-tool", "s1", now_ms(),
                  json.dumps({"type": "tool", "tool": "bash", "state": {"status": "running"}})))
    for qid, qstatus in (("p-q-p", "pending"), ("p-q-r", "running"),
                         ("p-q-completed", "completed"), ("p-q-replied", "replied"), ("p-q-error", "error")):
        conn.execute("INSERT INTO part(id, session_id, time_updated, data) VALUES(?,?,?,?)",
                     (qid, "s1", now_ms(),
                      json.dumps({"type": "tool", "tool": "question", "state": {"status": qstatus}})))
    for pid, pstatus in (("p-p-p", "pending"), ("p-p-r", "running"),
                         ("p-p-replied", "replied"), ("p-p-rejected", "rejected"), ("p-p-error", "error")):
        conn.execute("INSERT INTO part(id, session_id, time_updated, data) VALUES(?,?,?,?)",
                     (pid, "s1", now_ms(),
                      json.dumps({"type": "tool", "tool": "permission", "state": {"status": pstatus}})))
    conn.commit()
    st = DbObserver(db).snapshot_by_directory()["/d/fullspace"]
    assert st.status is Status.BUSY
    assert st.has_pending_input is True
    assert len(st.pending_questions) == 2  # pending + running; 3 resolved excluded
    assert len(st.pending_permissions) == 2  # pending + running; 3 resolved excluded


def test_multiple_running_tools_are_busy(tmp_path):
    # a session with two running tools is still BUSY (the active-tool tally is 2,
    # not 1, but the status is BUSY either way -- the count drives the tally, the
    # presence drives the status). Distinct part ids so the add helper doesn't
    # collide on its len(data)-derived id.
    db, conn = make_db(tmp_path)
    add_session(conn, "s1", "/d/multi")
    conn.execute("INSERT INTO part(id, session_id, time_updated, data) VALUES(?,?,?,?)",
                 ("t1", "s1", now_ms(),
                  json.dumps({"type": "tool", "tool": "bash", "state": {"status": "running"}})))
    conn.execute("INSERT INTO part(id, session_id, time_updated, data) VALUES(?,?,?,?)",
                 ("t2", "s1", now_ms(),
                  json.dumps({"type": "tool", "tool": "bash", "state": {"status": "running"}})))
    conn.commit()
    st = DbObserver(db).snapshot_by_directory()["/d/multi"]
    assert st.status is Status.BUSY


def test_pending_tool_is_busy(tmp_path):
    # a tool in "pending" status (queued, not yet running) still counts as an
    # active tool: the observer's active-tool tally includes pending tools, so a
    # queued tool keeps the TUI busy (green), not idle.
    db, conn = make_db(tmp_path)
    add_session(conn, "s1", "/d/pt")
    add_part(conn, "s1", {"type": "tool", "tool": "bash", "state": {"status": "pending"}})
    st = DbObserver(db).snapshot_by_directory()["/d/pt"]
    assert st.status is Status.BUSY


def test_missing_db_returns_empty_snapshot(tmp_path):
    # a DbObserver pointing at a nonexistent DB file (OpenCode has not written its
    # store yet) returns an empty snapshot -- no crash, no phantom session -- so
    # the broker's refresh treats it as "no OpenCode running" and shows all black.
    obs = DbObserver(tmp_path / "does-not-exist.db")
    assert obs.snapshot_by_directory() == {}


def test_multi_session_active_tool_folded(tmp_path):
    # a directory with two live sessions where one has a running tool (and the
    # other is idle): the active-tool count is folded across all live sessions in
    # the directory, so the directory is BUSY (a child still executing keeps the
    # owning TUI busy without taking a separate slot).
    db, conn = make_db(tmp_path)
    add_session(conn, "s-idle", "/d/fold")
    add_session(conn, "s-busy", "/d/fold")
    add_part(conn, "s-busy", {"type": "tool", "tool": "bash", "state": {"status": "running"}})
    st = DbObserver(db).snapshot_by_directory()["/d/fold"]
    assert st.status is Status.BUSY  # the running tool from either session drives it


def test_fresh_session_with_no_parts_is_idle(tmp_path):
    # a session with no parts (a fresh TUI that has not done anything yet) is
    # IDLE -- no running tool, no pending request, no recent activity -- so the
    # launch shows amber, ready for the first prompt.
    db, conn = make_db(tmp_path)
    add_session(conn, "s1", "/d/fresh")
    st = DbObserver(db).snapshot_by_directory()["/d/fresh"]
    assert st.has_session is True
    assert st.status is Status.IDLE
    assert st.has_pending_input is False


def test_archived_session_is_excluded(tmp_path):
    # a session that has been archived (time_archived set) is no longer a live
    # TUI: the observer's query filters it out, so its directory does not appear
    # in the snapshot at all (a stale TUI must not hold a slot).
    db, conn = make_db(tmp_path)
    add_session(conn, "live", "/d/live")
    add_session(conn, "arch", "/d/arch", archived=now_ms())
    snap = DbObserver(db).snapshot_by_directory()
    assert "/d/live" in snap
    assert "/d/arch" not in snap


def test_archived_session_pending_request_does_not_fold(tmp_path):
    # a live session and an archived session share one directory, and only the
    # ARCHIVED one has a pending question: the observer filters archived sessions
    # out of the query, so the stale TUI's pending request does NOT fold into the
    # live slot. The slot stays idle with has_pending_input False.
    db, conn = make_db(tmp_path)
    add_session(conn, "live", "/d/shared")
    add_session(conn, "arch", "/d/shared", archived=now_ms())
    # only the archived session has a pending question
    add_part(conn, "arch", {"type": "tool", "tool": "question", "state": {"status": "pending"}})
    st = DbObserver(db).snapshot_by_directory()["/d/shared"]
    assert st.has_session
    assert st.has_pending_input is False
    assert st.pending_questions == []


def test_default_db_path_honors_env_and_falls_back(monkeypatch):
    # default_db_path() honors the OPENCODE_DB env var (a non-default store) and
    # falls back to the global OpenCode DB location when unset -- the broker's
    # config.db() relies on this same fallback.
    from opendeck_broker.opencode.observe import default_db_path

    monkeypatch.setenv("OPENCODE_DB", "C:/custom/store.db")
    assert default_db_path() == Path("C:/custom/store.db")
    monkeypatch.delenv("OPENCODE_DB", raising=False)
    p = default_db_path()
    assert p.name == "opencode.db"  # the global OpenCode DB location


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
