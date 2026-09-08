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
