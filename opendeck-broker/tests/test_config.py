import os
from pathlib import Path

from opendeck_broker.config import Config


def test_db_explicit_path_and_default(monkeypatch):
    # db() honors an explicit db_path; with none it falls back to the OpenCode
    # global DB location (default_db_path).
    monkeypatch.delenv("OPENCODE_DB", raising=False)
    assert Config(db_path="/explicit/oc.db").db() == Path("/explicit/oc.db")
    assert Config().db().name == "opencode.db"  # no explicit path -> default location


def test_from_env_reads_documented_vars(monkeypatch):
    monkeypatch.setenv("OPENDECK_BROKER_HOST", "127.0.0.1")
    monkeypatch.setenv("OPENDECK_BROKER_PORT", "9999")
    monkeypatch.setenv("OPENDECK_KEY_SIZE", "96")
    monkeypatch.setenv("OPENCODE_DB", "C:/tmp/x.db")
    monkeypatch.setenv("OPENDECK_MINI_SERIAL", "ABC123")
    monkeypatch.setenv("OPENDECK_HEARTBEAT_S", "3")
    c = Config.from_env()
    assert c.host == "127.0.0.1"
    assert c.port == 9999
    assert c.image_size == 96
    assert c.device_serial == "ABC123"
    assert c.heartbeat_seconds == 3.0
    assert "x.db" in str(c.db())


def test_defaults(monkeypatch):
    for var in (
        "OPENDECK_BROKER_HOST",
        "OPENDECK_BROKER_PORT",
        "OPENDECK_KEY_SIZE",
        "OPENCODE_DB",
        "OPENDECK_MINI_SERIAL",
        "OPENDECK_HEARTBEAT_S",
        "OPENDECK_LEASE_S",
    ):
        monkeypatch.delenv(var, raising=False)
    c = Config.from_env()
    assert c.host == "127.0.0.1"
    assert c.port == 8899
    assert c.device_serial is None
    assert c.heartbeat_seconds == 2.0
    assert c.lease_seconds == 10.0


def test_tick_default_meets_500ms_state_target(monkeypatch):
    monkeypatch.delenv("OPENDECK_TICK_S", raising=False)
    c = Config.from_env()
    # research section 14: state updates within 500 ms, exit clears within 1 s
    assert c.tick_seconds <= 0.5
    assert c.tick_seconds > 0


def test_tick_env_override(monkeypatch):
    monkeypatch.setenv("OPENDECK_TICK_S", "0.25")
    assert Config.from_env().tick_seconds == 0.25


def test_token_is_stable_and_local(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENDECK_BROKER_HOME", str(tmp_path))
    c = Config()
    t1 = c.token()
    t2 = c.token()
    assert t1 == t2  # persisted, not regenerated
    assert len(t1) >= 16
    # stored under the broker home
    assert (tmp_path / "token").exists()
