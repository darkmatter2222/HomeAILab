import json
import os
import urllib.request

import pytest

from opendeck_broker.api import ApiServer
from opendeck_broker.broker import Broker
from opendeck_broker.config import Config
from opendeck_broker.device.mock import MockDevice
from opendeck_broker.focus.windows import WindowsFocusAdapter
from opendeck_broker.opencode.adapter import OpenCodeAdapter
from opendeck_broker.opencode.observe import DbObserver
from opendeck_broker.registry import Registry


@pytest.fixture
def server(tmp_path, monkeypatch):
    # isolate the token store
    monkeypatch.setenv("OPENDECK_BROKER_HOME", str(tmp_path))
    cfg = Config.from_env()
    cfg.port = 0
    reg = Registry()
    adapter = OpenCodeAdapter(reg, DbObserver(tmp_path / "no.db"))
    device = MockDevice()
    focus = WindowsFocusAdapter(
        enumerate_windows=lambda cb: [cb(1, "[opencode:homeai] x") or True],
        show_window=lambda h, c=9: True,
        set_foreground=lambda h: True,
        get_foreground=lambda: 1,
    )
    broker = Broker(registry=reg, device=device, focus=focus)
    api = ApiServer(broker, adapter, cfg)
    port = api.start(port=0)
    yield api, port, broker
    api.stop()


def req(method, url, token, body=None):
    import urllib.error

    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, method=method, headers={"X-OpenDeck-Token": token})
    if data is not None:
        r.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(r) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "{}")


def mk_focus(windows, fg):
    def enumerate(cb):
        for hwnd, title in windows:
            if not cb(hwnd, title):
                break

    return WindowsFocusAdapter(
        enumerate_windows=enumerate,
        show_window=lambda h, c=9: True,
        set_foreground=lambda h: True,
        get_foreground=lambda: fg,
    )


def test_sse_event_wire_format():
    # the SSE event formatter is the exact bytes the deck consumer parses: it
    # must be a "data: {json}\n\n" frame with the payload intact.
    from opendeck_broker.api import _Handler

    data = _Handler._event({"type": "snapshot", "frame": [{"slot": 0, "appearance": "black"}]})
    assert data.startswith(b"data: ")
    assert data.endswith(b"\n\n")
    assert json.loads(data[len(b"data: "):-2]) == {
        "type": "snapshot",
        "frame": [{"slot": 0, "appearance": "black"}],
    }


def test_api_server_exposes_token_and_port(server):
    # the ApiServer accessors the launcher/consumer rely on: a non-empty token
    # and the actual bound port (0 -> an ephemeral port was chosen).
    api, port, _ = server
    assert api.port() == port
    assert isinstance(api.token, str) and api.token


def test_api_body_malformed_valid_and_empty():
    # _body parses the JSON request body; a malformed body or an absent body
    # returns {} so a bad request doesn't crash the handler, and a valid body is
    # returned as the parsed dict.
    import io

    from opendeck_broker.api import _Handler

    h = _Handler.__new__(_Handler)
    h.headers = {"Content-Length": "8"}
    h.rfile = io.BytesIO(b"not json")
    assert h._body() == {}

    h2 = _Handler.__new__(_Handler)
    h2.headers = {"Content-Length": "9"}
    h2.rfile = io.BytesIO(b'{"a": 1}')
    assert h2._body() == {"a": 1}

    h3 = _Handler.__new__(_Handler)
    h3.headers = {}
    h3.rfile = io.BytesIO(b"")
    assert h3._body() == {}


def test_unknown_paths_are_404_and_wrong_token_is_401(server):
    # the routing fall-throughs: a GET/POST to an unknown path is a 404 (with a
    # valid token), and a request with the wrong/absent token is a 401 before
    # routing (the loopback API is token-gated, not path-gated).
    api, port, broker = server
    token = api.token
    base = f"http://127.0.0.1:{port}"
    # unknown GET path -> 404
    assert req("GET", f"{base}/v1/nope", token)[0] == 404
    # unknown POST path -> 404
    assert req("POST", f"{base}/v1/nope", token, {"x": 1})[0] == 404
    # wrong token -> 401 (even on a real path)
    assert req("GET", f"{base}/v1/display", "wrong-token")[0] == 401


def test_register_with_empty_body_uses_defaults(server):
    # the register endpoint tolerates an empty body (a producer that sends no
    # directory/alias/pid): it still creates an instance with the defaults and
    # returns a fresh instanceId + a valid slot, not a crash.
    api, port, broker = server
    token = api.token
    base = f"http://127.0.0.1:{port}"
    st, reg = req("POST", f"{base}/v1/instances/register", token, {})
    assert st == 200
    assert reg["instanceId"]  # a fresh identity was minted
    assert reg["slot"] in (0, 1, 2, 3, 4, 5)


def test_register_with_focus_target_binds_marker(server):
    # a producer may register with a pre-known focusTarget (e.g. the launcher
    # already minted the window-title marker): the instance's focus_target then
    # carries that marker, so a later press focuses the right window.
    api, port, broker = server
    token = api.token
    base = f"http://127.0.0.1:{port}"
    st, reg = req("POST", f"{base}/v1/instances/register", token,
                  {"directory": "/d/x", "focusTarget": {"opaqueId": "my-marker"}})
    assert st == 200
    iid = reg["instanceId"]
    assert broker.registry.instances[iid].focus_target["opaqueId"] == "my-marker"


def test_register_with_start_time_stores_it(server):
    # a producer that registers with a startTime (the TUI process start time)
    # has it stored on the instance's process, so the liveness check can use it.
    api, port, broker = server
    token = api.token
    base = f"http://127.0.0.1:{port}"
    st, reg = req("POST", f"{base}/v1/instances/register", token,
                  {"directory": "/d/x", "alias": "x", "pid": 1, "startTime": 12345678})
    assert st == 200
    iid = reg["instanceId"]
    assert broker.registry.instances[iid].process.start_time == 12345678


def test_register_without_focus_target_mints_marker(server):
    # a producer that registers WITHOUT a pre-known focusTarget gets a minted
    # marker (opencode:<alias>-<6char>) on the instance, so a later press can
    # still focus the right window -- parallel to the provided-focusTarget case.
    api, port, broker = server
    token = api.token
    base = f"http://127.0.0.1:{port}"
    st, reg = req("POST", f"{base}/v1/instances/register", token,
                  {"directory": "/d/x", "alias": "x"})
    assert st == 200
    iid = reg["instanceId"]
    marker = broker.registry.instances[iid].focus_target["opaqueId"]
    assert marker.startswith("opencode:x-")  # minted, not pre-known


def test_focus_endpoint_no_matching_window_is_not_found(server):
    # the /v1/focus endpoint resolves a press for a registered instance. The
    # fixture's focus adapter has a window that does NOT carry this instance's
    # marker, so the outcome is NOT_FOUND (no window to focus) -- a valid 200.
    api, port, broker = server
    token = api.token
    base = f"http://127.0.0.1:{port}"
    st, reg = req("POST", f"{base}/v1/instances/register", token,
                  {"directory": "/d/x", "alias": "x", "pid": 1})
    iid = reg["instanceId"]
    gen = broker.registry.resolve(iid).generation
    st, res = req("POST", f"{base}/v1/focus", token,
                  {"instanceId": iid, "expectedGeneration": gen})
    assert st == 200
    assert res["status"] == "not_found"  # the fixture window lacks this marker


def test_focus_endpoint_success_when_window_matches(server):
    # the /v1/focus endpoint resolves a press to a focus outcome. When the
    # focus adapter's window carries the instance's marker, the outcome is
    # SUCCESS (the window was focused).
    api, port, broker = server
    token = api.token
    base = f"http://127.0.0.1:{port}"
    st, reg = req("POST", f"{base}/v1/instances/register", token,
                  {"directory": "/d/x", "focusTarget": {"opaqueId": "opencode:homeai"}})
    iid = reg["instanceId"]
    gen = broker.registry.resolve(iid).generation
    st, res = req("POST", f"{base}/v1/focus", token,
                  {"instanceId": iid, "expectedGeneration": gen})
    assert st == 200
    assert res["status"] == "success"


def test_focus_endpoint_ambiguous_when_multiple_windows_match(server):
    # the /v1/focus endpoint resolves a press to a focus outcome. When the
    # focus adapter finds multiple windows carrying the same marker, the
    # outcome is AMBIGUOUS (can't tell which window to focus).
    api, port, broker = server
    token = api.token
    base = f"http://127.0.0.1:{port}"
    broker.focus = WindowsFocusAdapter(
        enumerate_windows=lambda cb: [cb(1, "[opencode:homeai] x") or True,
                                      cb(2, "[opencode:homeai] y") or True],
        show_window=lambda h, c=9: True,
        set_foreground=lambda h: True,
        get_foreground=lambda: 1,
    )
    st, reg = req("POST", f"{base}/v1/instances/register", token,
                  {"directory": "/d/x", "focusTarget": {"opaqueId": "opencode:homeai"}})
    iid = reg["instanceId"]
    gen = broker.registry.resolve(iid).generation
    st, res = req("POST", f"{base}/v1/focus", token,
                  {"instanceId": iid, "expectedGeneration": gen})
    assert st == 200
    assert res["status"] == "ambiguous"


def test_display_with_no_instances_is_all_black(server):
    # with no registered instances, the display frame is all six slots black
    # (nothing to show).
    api, port, broker = server
    token = api.token
    base = f"http://127.0.0.1:{port}"
    st, disp = req("GET", f"{base}/v1/display", token)
    assert st == 200
    assert len(disp["frame"]) == 6
    assert all(s["appearance"] == "black" for s in disp["frame"])


def test_register_overflow_when_all_slots_full(server):
    # registering a 7th instance when all six slots are occupied overflows:
    # the registry reports the overflow (no free slot), not a crash.
    api, port, broker = server
    token = api.token
    base = f"http://127.0.0.1:{port}"
    for i in range(6):
        st, _ = req("POST", f"{base}/v1/instances/register", token,
                    {"directory": f"/d/{i}", "alias": f"a{i}", "pid": 1000 + i})
        assert st == 200
    # the 7th register overflows (no free slot)
    st, res = req("POST", f"{base}/v1/instances/register", token,
                  {"directory": "/d/overflow", "alias": "ovf", "pid": 2000})
    assert st == 200
    assert res["slot"] is None  # no free slot -> overflow


def test_display_multiple_instances_use_distinct_slots(server):
    # with multiple registered instances, each is assigned its own slot (not
    # all in slot 0) and the display reflects both.
    api, port, broker = server
    token = api.token
    base = f"http://127.0.0.1:{port}"
    st, reg1 = req("POST", f"{base}/v1/instances/register", token,
                   {"directory": "/d/a", "alias": "a", "pid": 1001})
    st, reg2 = req("POST", f"{base}/v1/instances/register", token,
                   {"directory": "/d/b", "alias": "b", "pid": 1002})
    assert reg1["slot"] != reg2["slot"]  # distinct slots
    st, disp = req("GET", f"{base}/v1/display", token)
    assert st == 200 and len(disp["frame"]) == 6
    # both occupied slots are non-black (each has a live instance)
    assert disp["frame"][reg1["slot"]]["appearance"] != "black"
    assert disp["frame"][reg2["slot"]]["appearance"] != "black"


def test_register_mints_a_fresh_instance_id_each_time(server):
    # each register mints a fresh instanceId (even for the same directory):
    # the broker tracks instances by id, not by directory.
    api, port, broker = server
    token = api.token
    base = f"http://127.0.0.1:{port}"
    st, reg1 = req("POST", f"{base}/v1/instances/register", token,
                   {"directory": "/d/same", "alias": "a", "pid": 1001})
    st, reg2 = req("POST", f"{base}/v1/instances/register", token,
                   {"directory": "/d/same", "alias": "a", "pid": 1001})
    assert reg1["instanceId"] != reg2["instanceId"]  # fresh ids
    assert reg1["slot"] != reg2["slot"]  # distinct slots


def test_snapshot_for_deleted_instance_is_404(server):
    # a snapshot for a deleted (freed) instance is a 404 (the instance is gone;
    # the producer should re-register).
    api, port, broker = server
    token = api.token
    base = f"http://127.0.0.1:{port}"
    st, reg = req("POST", f"{base}/v1/instances/register", token,
                  {"directory": "/d/x", "alias": "x", "pid": 1})
    iid = reg["instanceId"]
    req("DELETE", f"{base}/v1/instances/{iid}", token)  # free the instance
    st, res = req("PUT", f"{base}/v1/instances/{iid}/snapshot", token,
                  {"status": "busy"})
    assert st == 404


def test_display_slot_goes_black_when_instance_dies(server):
    # when a registered instance's process dies, its slot renders black (the
    # dead occupant is cleared from the frame).
    api, port, broker = server
    token = api.token
    base = f"http://127.0.0.1:{port}"
    st, reg = req("POST", f"{base}/v1/instances/register", token,
                  {"directory": "/d/x", "alias": "x", "pid": 1})
    slot = reg["slot"]
    # alive -> non-black
    st, disp = req("GET", f"{base}/v1/display", token)
    assert disp["frame"][slot]["appearance"] != "black"
    # kill the process -> the slot goes black on the next render
    broker.registry.instances[reg["instanceId"]].live = False
    broker.render()
    st, disp = req("GET", f"{base}/v1/display", token)
    assert disp["frame"][slot]["appearance"] == "black"


def test_diagnostics_reflects_multiple_registered_instances(server):
    # the /v1/diagnostics endpoint reflects the full registry state: with
    # multiple instances, the diagnostics show each registered slot.
    api, port, broker = server
    token = api.token
    base = f"http://127.0.0.1:{port}"
    st, reg1 = req("POST", f"{base}/v1/instances/register", token,
                   {"directory": "/d/a", "alias": "a", "pid": 1001})
    st, reg2 = req("POST", f"{base}/v1/instances/register", token,
                   {"directory": "/d/b", "alias": "b", "pid": 1002})
    st, diag = req("GET", f"{base}/v1/diagnostics", token)
    assert st == 200
    slots = diag["registry"]["slots"]
    assert len(slots) == 6
    assert slots[reg1["slot"]]["instance_id"] == reg1["instanceId"]
    assert slots[reg2["slot"]]["instance_id"] == reg2["instanceId"]


def test_delete_unknown_instance_is_404(server):
    # deleting an unknown instance is a 404 (the broker has no record of it).
    api, port, broker = server
    token = api.token
    base = f"http://127.0.0.1:{port}"
    st, res = req("DELETE", f"{base}/v1/instances/nonexistent", token)
    assert st == 404


def test_snapshot_input_appearance_with_pending_question(server):
    # a snapshot with a pending question renders the slot as "input" (the
    # instance is waiting for the user's answer).
    api, port, broker = server
    token = api.token
    base = f"http://127.0.0.1:{port}"
    st, reg = req("POST", f"{base}/v1/instances/register", token,
                  {"directory": "/d/x", "alias": "x", "pid": 1})
    iid, slot = reg["instanceId"], reg["slot"]
    st, snap = req("PUT", f"{base}/v1/instances/{iid}/snapshot", token,
                   {"status": "idle", "pendingQuestionIds": ["q1"]})
    assert st == 200 and snap["applied"] is True
    st, disp = req("GET", f"{base}/v1/display", token)
    assert disp["frame"][slot]["appearance"] == "input"


def test_snapshot_with_pending_permission_shows_input(server):
    # a snapshot with a pending permission also renders the slot as "input"
    # (the instance is waiting for the user's permission grant).
    api, port, broker = server
    token = api.token
    base = f"http://127.0.0.1:{port}"
    st, reg = req("POST", f"{base}/v1/instances/register", token,
                  {"directory": "/d/x", "alias": "x", "pid": 1})
    iid, slot = reg["instanceId"], reg["slot"]
    st, snap = req("PUT", f"{base}/v1/instances/{iid}/snapshot", token,
                   {"status": "busy", "pendingPermissionIds": ["p1"]})
    assert st == 200 and snap["applied"] is True
    st, disp = req("GET", f"{base}/v1/display", token)
    assert disp["frame"][slot]["appearance"] == "input"


def test_snapshot_error_state_still_renders(server):
    # a snapshot with an error set still renders (the error is recorded but the
    # slot shows the status appearance, not a crash).
    api, port, broker = server
    token = api.token
    base = f"http://127.0.0.1:{port}"
    st, reg = req("POST", f"{base}/v1/instances/register", token,
                  {"directory": "/d/x", "alias": "x", "pid": 1})
    iid, slot = reg["instanceId"], reg["slot"]
    st, snap = req("PUT", f"{base}/v1/instances/{iid}/snapshot", token,
                   {"status": "busy", "error": "connection lost"})
    assert st == 200 and snap["applied"] is True
    st, disp = req("GET", f"{base}/v1/display", token)
    # the error is recorded but the slot still renders (busy -> run)
    assert disp["frame"][slot]["appearance"] == "run"


def test_display_slot_shows_unknown_when_telemetry_untrusted(server):
    # when the instance's telemetry is not trustworthy (transport disconnected),
    # the slot renders "unknown" (amber with "?"), not idle or run.
    api, port, broker = server
    token = api.token
    base = f"http://127.0.0.1:{port}"
    st, reg = req("POST", f"{base}/v1/instances/register", token,
                  {"directory": "/d/x", "alias": "x", "pid": 1})
    iid, slot = reg["instanceId"], reg["slot"]
    broker.registry.instances[iid].telemetry_trusted = False
    broker.render()
    st, disp = req("GET", f"{base}/v1/display", token)
    assert disp["frame"][slot]["appearance"] == "unknown"


def test_snapshot_retry_status_shows_run(server):
    # a snapshot with a retry status also renders the slot as "run" (the
    # instance is retrying, which is a busy state -- not idle).
    api, port, broker = server
    token = api.token
    base = f"http://127.0.0.1:{port}"
    st, reg = req("POST", f"{base}/v1/instances/register", token,
                  {"directory": "/d/x", "alias": "x", "pid": 1})
    iid, slot = reg["instanceId"], reg["slot"]
    st, snap = req("PUT", f"{base}/v1/instances/{iid}/snapshot", token,
                   {"status": "retry"})
    assert st == 200 and snap["applied"] is True
    st, disp = req("GET", f"{base}/v1/display", token)
    assert disp["frame"][slot]["appearance"] == "run"


def test_register_assigns_slots_in_order(server):
    # registering instances assigns slots in order (0, 1, 2, ...), not
    # randomly.
    api, port, broker = server
    token = api.token
    base = f"http://127.0.0.1:{port}"
    slots = []
    for i in range(4):
        st, reg = req("POST", f"{base}/v1/instances/register", token,
                      {"directory": f"/d/{i}", "alias": f"a{i}", "pid": 1000 + i})
        slots.append(reg["slot"])
    assert slots == [0, 1, 2, 3]  # sequential assignment


def test_register_reuses_freed_slot(server):
    # when an instance is freed (deleted), a new register reuses the freed
    # slot (not a new one).
    api, port, broker = server
    token = api.token
    base = f"http://127.0.0.1:{port}"
    st, reg1 = req("POST", f"{base}/v1/instances/register", token,
                   {"directory": "/d/a", "alias": "a", "pid": 1001})
    slot1 = reg1["slot"]
    req("DELETE", f"{base}/v1/instances/{reg1['instanceId']}", token)  # free slot1
    st, reg2 = req("POST", f"{base}/v1/instances/register", token,
                   {"directory": "/d/b", "alias": "b", "pid": 1002})
    assert reg2["slot"] == slot1  # the freed slot is reused


def test_register_with_long_alias_still_registers(server):
    # a long alias still registers (the display label is truncated for rendering,
    # but the registration succeeds).
    api, port, broker = server
    token = api.token
    base = f"http://127.0.0.1:{port}"
    long_alias = "a" * 200
    st, reg = req("POST", f"{base}/v1/instances/register", token,
                  {"directory": "/d/long", "alias": long_alias, "pid": 1})
    assert st == 200
    assert reg["instanceId"]  # registered successfully
    assert reg["slot"] in (0, 1, 2, 3, 4, 5)


def test_register_with_empty_alias_still_registers(server):
    # an empty alias still registers (the display label falls back to a default,
    # but the registration succeeds).
    api, port, broker = server
    token = api.token
    base = f"http://127.0.0.1:{port}"
    st, reg = req("POST", f"{base}/v1/instances/register", token,
                  {"directory": "/d/noalias", "alias": "", "pid": 1})
    assert st == 200
    assert reg["instanceId"]  # registered successfully
    assert reg["slot"] in (0, 1, 2, 3, 4, 5)


def test_register_with_special_chars_in_directory_still_registers(server):
    # a directory with special characters (spaces, unicode) still registers
    # (the directory is used as a key, not parsed).
    api, port, broker = server
    token = api.token
    base = f"http://127.0.0.1:{port}"
    st, reg = req("POST", f"{base}/v1/instances/register", token,
                  {"directory": "/d/my project (copy)/ünïcode", "alias": "sp", "pid": 1})
    assert st == 200
    assert reg["instanceId"]  # registered successfully


def test_register_with_no_observer_still_registers(server):
    # when the observer has no DB (no sessions), registering still succeeds
    # (the slot starts idle -- no observer data to drive it busy).
    api, port, broker = server
    token = api.token
    base = f"http://127.0.0.1:{port}"
    st, reg = req("POST", f"{base}/v1/instances/register", token,
                  {"directory": "/d/noobserver", "alias": "noobs", "pid": 1})
    assert st == 200
    assert reg["instanceId"]  # registered successfully
    assert reg["slot"] in (0, 1, 2, 3, 4, 5)


def test_register_with_boolean_directory_value_still_registers(server):
    # a directory that's a boolean value still registers (stored as-is).
    api, port, broker = server
    token = api.token
    base = f"http://127.0.0.1:{port}"
    st, reg = req("POST", f"{base}/v1/instances/register", token,
                  {"directory": True, "alias": "boolval", "pid": 1})
    assert st == 200
    assert reg["instanceId"]  # registered successfully


def test_register_with_null_directory_value_still_registers(server):
    # a directory that's a JSON null value still registers (stored as-is).
    api, port, broker = server
    token = api.token
    base = f"http://127.0.0.1:{port}"
    st, reg = req("POST", f"{base}/v1/instances/register", token,
                  {"directory": None, "alias": "nullval", "pid": 1})
    assert st == 200
    assert reg["instanceId"]  # registered successfully


def test_register_with_null_byte_directory_still_registers(server):
    # a directory with a null byte still registers (the path is stored as-is).
    api, port, broker = server
    token = api.token
    base = f"http://127.0.0.1:{port}"
    st, reg = req("POST", f"{base}/v1/instances/register", token,
                  {"directory": "/d/null\0byte", "alias": "nulldir", "pid": 1})
    assert st == 200
    assert reg["instanceId"]  # registered successfully


def test_register_with_newline_in_directory_still_registers(server):
    # a directory with a newline character still registers (the path is stored as-is).
    api, port, broker = server
    token = api.token
    base = f"http://127.0.0.1:{port}"
    st, reg = req("POST", f"{base}/v1/instances/register", token,
                  {"directory": "/d/new\nline", "alias": "newline", "pid": 1})
    assert st == 200
    assert reg["instanceId"]  # registered successfully


def test_register_with_tab_in_directory_still_registers(server):
    # a directory with a tab character still registers (the path is stored as-is).
    api, port, broker = server
    token = api.token
    base = f"http://127.0.0.1:{port}"
    st, reg = req("POST", f"{base}/v1/instances/register", token,
                  {"directory": "/d/tab\there", "alias": "tabdir", "pid": 1})
    assert st == 200
    assert reg["instanceId"]  # registered successfully


def test_register_with_trailing_space_directory_still_registers(server):
    # a directory with a trailing space still registers (the path is stored as-is).
    api, port, broker = server
    token = api.token
    base = f"http://127.0.0.1:{port}"
    st, reg = req("POST", f"{base}/v1/instances/register", token,
                  {"directory": "trailing/space ", "alias": "trailsp", "pid": 1})
    assert st == 200
    assert reg["instanceId"]  # registered successfully


def test_register_with_leading_space_directory_still_registers(server):
    # a directory with a leading space still registers (the path is stored as-is).
    api, port, broker = server
    token = api.token
    base = f"http://127.0.0.1:{port}"
    st, reg = req("POST", f"{base}/v1/instances/register", token,
                  {"directory": " leading/space", "alias": "leadsp", "pid": 1})
    assert st == 200
    assert reg["instanceId"]  # registered successfully


def test_register_with_drive_root_directory_still_registers(server):
    # a directory that's a drive root (C:\) still registers (stored as-is).
    api, port, broker = server
    token = api.token
    base = f"http://127.0.0.1:{port}"
    st, reg = req("POST", f"{base}/v1/instances/register", token,
                  {"directory": "C:\\", "alias": "driveroot", "pid": 1})
    assert st == 200
    assert reg["instanceId"]  # registered successfully


def test_register_with_tilde_directory_still_registers(server):
    # a directory that's a tilde (~) still registers (the path is stored as-is).
    api, port, broker = server
    token = api.token
    base = f"http://127.0.0.1:{port}"
    st, reg = req("POST", f"{base}/v1/instances/register", token,
                  {"directory": "~/proj", "alias": "tilde", "pid": 1})
    assert st == 200
    assert reg["instanceId"]  # registered successfully


def test_register_with_double_dot_directory_still_registers(server):
    # a directory that's a double dot (parent dir) still registers (stored as-is).
    api, port, broker = server
    token = api.token
    base = f"http://127.0.0.1:{port}"
    st, reg = req("POST", f"{base}/v1/instances/register", token,
                  {"directory": "..", "alias": "dotdot", "pid": 1})
    assert st == 200
    assert reg["instanceId"]  # registered successfully


def test_register_with_dot_directory_still_registers(server):
    # a directory that's a dot (current dir) still registers (stored as-is).
    api, port, broker = server
    token = api.token
    base = f"http://127.0.0.1:{port}"
    st, reg = req("POST", f"{base}/v1/instances/register", token,
                  {"directory": ".", "alias": "dotdir", "pid": 1})
    assert st == 200
    assert reg["instanceId"]  # registered successfully


def test_register_with_double_slash_directory_still_registers(server):
    # a directory with a double slash still registers (the path is stored as-is).
    api, port, broker = server
    token = api.token
    base = f"http://127.0.0.1:{port}"
    st, reg = req("POST", f"{base}/v1/instances/register", token,
                  {"directory": "/d//double//slash", "alias": "dbl", "pid": 1})
    assert st == 200
    assert reg["instanceId"]  # registered successfully


def test_register_with_hidden_directory_still_registers(server):
    # a directory with a leading dot (hidden) still registers (stored as-is).
    api, port, broker = server
    token = api.token
    base = f"http://127.0.0.1:{port}"
    st, reg = req("POST", f"{base}/v1/instances/register", token,
                  {"directory": "/d/.hidden/proj", "alias": "hidden", "pid": 1})
    assert st == 200
    assert reg["instanceId"]  # registered successfully


def test_register_with_relative_directory_still_registers(server):
    # a relative path still registers (the path is stored as-is).
    api, port, broker = server
    token = api.token
    base = f"http://127.0.0.1:{port}"
    st, reg = req("POST", f"{base}/v1/instances/register", token,
                  {"directory": "sub/dir", "alias": "relative", "pid": 1})
    assert st == 200
    assert reg["instanceId"]  # registered successfully


def test_register_with_unc_network_directory_still_registers(server):
    # a UNC network path still registers (the path is stored as-is).
    api, port, broker = server
    token = api.token
    base = f"http://127.0.0.1:{port}"
    st, reg = req("POST", f"{base}/v1/instances/register", token,
                  {"directory": "\\\\server\\share\\proj", "alias": "unc", "pid": 1})
    assert st == 200
    assert reg["instanceId"]  # registered successfully


def test_register_with_special_and_unicode_directory_still_registers(server):
    # a directory with both special characters and unicode still registers.
    api, port, broker = server
    token = api.token
    base = f"http://127.0.0.1:{port}"
    st, reg = req("POST", f"{base}/v1/instances/register", token,
                  {"directory": "/d/日本語/日本語/日本語", "alias": "mixed", "pid": 1})
    assert st == 200
    assert reg["instanceId"]  # registered successfully


def test_register_with_space_in_directory_still_registers(server):
    # a directory with a space still registers (the path is stored as-is).
    api, port, broker = server
    token = api.token
    base = f"http://127.0.0.1:{port}"
    st, reg = req("POST", f"{base}/v1/instances/register", token,
                  {"directory": "/d/my proj/sub dir", "alias": "spacedir", "pid": 1})
    assert st == 200
    assert reg["instanceId"]  # registered successfully


def test_register_with_mixed_slash_directory_still_registers(server):
    # a directory with mixed forward and back slashes still registers (stored as-is).
    api, port, broker = server
    token = api.token
    base = f"http://127.0.0.1:{port}"
    st, reg = req("POST", f"{base}/v1/instances/register", token,
                  {"directory": "C:\\Users\\ryans/proj", "alias": "mixed", "pid": 1})
    assert st == 200
    assert reg["instanceId"]  # registered successfully


def test_register_with_windows_style_directory_still_registers(server):
    # a Windows-style directory path still registers (the path is stored as-is).
    api, port, broker = server
    token = api.token
    base = f"http://127.0.0.1:{port}"
    st, reg = req("POST", f"{base}/v1/instances/register", token,
                  {"directory": "C:\\Users\\ryans\\proj", "alias": "winpath", "pid": 1})
    assert st == 200
    assert reg["instanceId"]  # registered successfully


def test_register_with_trailing_slash_directory_still_registers(server):
    # a directory with a trailing slash still registers (the path is stored as-is).
    api, port, broker = server
    token = api.token
    base = f"http://127.0.0.1:{port}"
    st, reg = req("POST", f"{base}/v1/instances/register", token,
                  {"directory": "/d/trailing/", "alias": "trailing", "pid": 1})
    assert st == 200
    assert reg["instanceId"]  # registered successfully


def test_register_with_empty_directory_still_registers(server):
    # an empty-string directory still registers (the path is stored as-is).
    api, port, broker = server
    token = api.token
    base = f"http://127.0.0.1:{port}"
    st, reg = req("POST", f"{base}/v1/instances/register", token,
                  {"directory": "", "alias": "emptydir", "pid": 1})
    assert st == 200
    assert reg["instanceId"]  # registered successfully


def test_register_with_unicode_directory_still_registers(server):
    # a directory with unicode characters still registers (the path is stored as-is).
    api, port, broker = server
    token = api.token
    base = f"http://127.0.0.1:{port}"
    st, reg = req("POST", f"{base}/v1/instances/register", token,
                  {"directory": "/d/日本語/中文/한국어", "alias": "unicode", "pid": 1})
    assert st == 200
    assert reg["instanceId"]  # registered successfully


def test_register_with_long_directory_still_registers(server):
    # a very long directory path still registers (the path is stored as-is).
    api, port, broker = server
    token = api.token
    base = f"http://127.0.0.1:{port}"
    long_dir = "/d/" + "a" * 200
    st, reg = req("POST", f"{base}/v1/instances/register", token,
                  {"directory": long_dir, "alias": "longdir", "pid": 1})
    assert st == 200
    assert reg["instanceId"]  # registered successfully


def test_register_with_numeric_alias_still_registers(server):
    # a numeric alias still registers (the alias is a string label, not a number).
    api, port, broker = server
    token = api.token
    base = f"http://127.0.0.1:{port}"
    st, reg = req("POST", f"{base}/v1/instances/register", token,
                  {"directory": "/d/num", "alias": "42", "pid": 1})
    assert st == 200
    assert reg["instanceId"]  # registered successfully


def test_register_display_focus_roundtrip(server):
    api, port, broker = server
    token = api.token
    base = f"http://127.0.0.1:{port}"

    st, reg = req("POST", f"{base}/v1/instances/register", token,
                  {"directory": "/d/homeai", "alias": "homeai", "pid": 1234})
    assert st == 200
    iid, slot = reg["instanceId"], reg["slot"]
    assert slot == 0

    # give the broker a focus adapter whose window carries the instance's real
    # unique launch-token marker (the realistic launcher->window-title binding)
    marker = broker.registry.instances[iid].focus_target["opaqueId"]
    broker.focus = mk_focus([(7, f"[{marker}] x")], 7)

    # display: home session absent -> amber (idle)
    st, disp = req("GET", f"{base}/v1/display", token)
    assert disp["frame"][0]["appearance"] in ("idle", "black")

    # push a busy snapshot
    st, snap = req("PUT", f"{base}/v1/instances/{iid}/snapshot", token,
                   {"status": "busy"})
    assert st == 200 and snap["applied"] is True
    st, disp = req("GET", f"{base}/v1/display", token)
    assert disp["frame"][0]["appearance"] == "run"

    # push a pending question -> input
    st, _ = req("PUT", f"{base}/v1/instances/{iid}/snapshot", token,
                {"status": "idle", "pendingQuestionIds": ["q1"]})
    st, disp = req("GET", f"{base}/v1/display", token)
    assert disp["frame"][0]["appearance"] == "input"

    # focus
    st, foc = req("POST", f"{base}/v1/focus", token, {"instanceId": iid})
    assert foc["status"] == "success"

    # diagnostics
    st, diag = req("GET", f"{base}/v1/diagnostics", token)
    assert st == 200 and diag["registry"]["slots"][0]["instance_id"] == iid


def test_focus_unknown_instance_is_stale(server):
    # research section 7: a press/focus accepts a known instance id, not an
    # arbitrary command. An unknown id must resolve to STALE, not crash or
    # claim success.
    api, port, broker = server
    token = api.token
    base = f"http://127.0.0.1:{port}"
    st, foc = req("POST", f"{base}/v1/focus", token,
                  {"instanceId": "does-not-exist"})
    assert st == 200
    assert foc["status"] == "stale"


def test_heartbeat_and_delete_via_api(server):
    # research section 7: the REST heartbeat and delete endpoints (previously
    # only exercised at the registry level, not the HTTP surface).
    api, port, broker = server
    token = api.token
    base = f"http://127.0.0.1:{port}"

    st, reg = req("POST", f"{base}/v1/instances/register", token,
                  {"directory": "/d/homeai", "alias": "homeai", "pid": os.getpid()})
    assert st == 200
    iid, slot = reg["instanceId"], reg["slot"]

    # heartbeat renews presence and returns the broker epoch
    st, hb = req("POST", f"{base}/v1/instances/{iid}/heartbeat", token)
    assert st == 200 and hb["broker_epoch"]

    # delete detaches the instance and frees its slot
    st, dele = req("DELETE", f"{base}/v1/instances/{iid}", token)
    assert st == 200 and dele["detached"] is True
    st, disp = req("GET", f"{base}/v1/display", token)
    assert disp["frame"][slot]["appearance"] in ("black", "idle")
    # a second delete of the same id is a 404 (already gone)
    st, dele2 = req("DELETE", f"{base}/v1/instances/{iid}", token)
    assert st == 404


def test_heartbeat_unknown_instance_is_404(server):
    # the heartbeat endpoint returns 404 for an unknown instance (the broker
    # has no record of it -- the producer should re-register).
    api, port, broker = server
    token = api.token
    base = f"http://127.0.0.1:{port}"
    st, res = req("POST", f"{base}/v1/instances/nonexistent/heartbeat", token)
    assert st == 404


def test_deck_sse_initial_snapshot(server):
    import http.client

    api, port, broker = server
    token = api.token
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request("GET", "/v1/deck", headers={"X-OpenDeck-Token": token})
    resp = conn.getresponse()
    try:
        assert resp.status == 200
        assert "text/event-stream" in (resp.getheader("Content-Type") or "")
        data = None
        for _ in range(8):
            line = resp.fp.readline().decode().strip()
            if line.startswith("data:"):
                data = line[5:].strip()
                break
        assert data is not None
        obj = json.loads(data)
        assert obj["type"] == "snapshot"
        assert len(obj["frame"]) == 6
    finally:
        conn.close()


def test_deck_sse_streams_state_changes(server):
    # the SSE /v1/deck endpoint must push a new frame when state changes (not
    # just the initial snapshot) -- the deck UI subscribes to this.
    import http.client

    api, port, broker = server
    token = api.token
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request("GET", "/v1/deck", headers={"X-OpenDeck-Token": token})
    resp = conn.getresponse()
    assert resp.status == 200

    def next_snapshot():
        for _ in range(16):
            line = resp.fp.readline().decode().strip()
            if not line:
                continue
            if line.startswith("data:"):
                return json.loads(line[5:].strip())
        return None

    try:
        initial = next_snapshot()
        assert initial is not None and initial["type"] == "snapshot"

        # trigger a state change on a separate connection; the open SSE stream
        # must receive the pushed frame
        st, reg = req("POST", f"http://127.0.0.1:{port}/v1/instances/register", token,
                      {"directory": "/d/homeai", "alias": "homeai", "pid": os.getpid()})
        assert st == 200
        iid = reg["instanceId"]
        req("PUT", f"http://127.0.0.1:{port}/v1/instances/{iid}/snapshot", token,
            {"status": "busy"})

        pushed = next_snapshot()
        assert pushed is not None and pushed["type"] == "snapshot"
    finally:
        conn.close()


def test_wrong_token_rejected(server):
    api, port, broker = server
    st, body = req("GET", f"http://127.0.0.1:{port}/v1/display", "wrong-token")
    assert st == 401


def test_stale_snapshot_conflict(server):
    api, port, broker = server
    token = api.token
    base = f"http://127.0.0.1:{port}"
    _, reg = req("POST", f"{base}/v1/instances/register", token,
                 {"directory": "/d/a", "alias": "a", "pid": 1})
    iid = reg["instanceId"]
    req("PUT", f"{base}/v1/instances/{iid}/snapshot", token, {"status": "busy"})
    # a second snapshot reuses the same seq internally via adapter; applied True
    st, snap = req("PUT", f"{base}/v1/instances/{iid}/snapshot", token, {"status": "idle"})
    assert st == 200 and snap["applied"] is True


def test_snapshot_unknown_instance_is_404(server):
    # a snapshot for an instance id the broker never registered is a clean 404,
    # not a crash or a 409 conflict.
    api, port, broker = server
    token = api.token
    base = f"http://127.0.0.1:{port}"
    st, body = req("PUT", f"{base}/v1/instances/does-not-exist/snapshot", token,
                   {"status": "busy"})
    assert st == 404
    assert body.get("error") == "not_found"
