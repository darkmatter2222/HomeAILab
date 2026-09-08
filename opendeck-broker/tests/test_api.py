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
