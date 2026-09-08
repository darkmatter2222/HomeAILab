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
    from opendeck_broker.images import DEFAULT_KEY_SIZE

    assert c.image_size == DEFAULT_KEY_SIZE  # 144, the Mini resolution


def test_malformed_numeric_env_fails_fast(monkeypatch):
    # a non-numeric port (or heartbeat) env value is a config error: from_env
    # raises rather than silently falling back to a wrong value.
    monkeypatch.setenv("OPENDECK_BROKER_PORT", "not-a-port")
    try:
        Config.from_env()
        raise AssertionError("expected ValueError")
    except ValueError:
        pass
    monkeypatch.setenv("OPENDECK_BROKER_PORT", "8899")
    monkeypatch.setenv("OPENDECK_HEARTBEAT_S", "not-a-number")
    try:
        Config.from_env()
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


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


def test_token_strips_surrounding_whitespace(monkeypatch, tmp_path):
    # a persisted token file with leading/trailing whitespace is stripped before
    # use (so a trailing newline from an editor doesn't leak into the API token),
    # and the stripped value is stable across calls.
    monkeypatch.setenv("OPENDECK_BROKER_HOME", str(tmp_path))
    (tmp_path / "token").write_text("  abcdef0123456789  \n")
    c = Config()
    assert c.token() == "abcdef0123456789"
    assert c.token() == "abcdef0123456789"  # stable


def test_token_recreates_when_blank(monkeypatch, tmp_path):
    # a token file that is blank (empty or whitespace-only) is treated as
    # unset: token() mints a fresh token and persists it (not the blank value).
    monkeypatch.setenv("OPENDECK_BROKER_HOME", str(tmp_path))
    (tmp_path / "token").write_text("   \n")
    t = Config().token()
    assert t.strip() == t  # no surrounding whitespace
    assert t != ""  # a fresh token, not the blank value
    assert (tmp_path / "token").read_text().strip() == t  # persisted


def test_token_fallback_when_store_unwritable(monkeypatch, tmp_path):
    # if the token store can't be read/written (a permissions error, or the path
    # is occupied), token() falls back to a fresh in-memory token rather than
    # crashing -- the broker can still gate the loopback API.
    monkeypatch.setenv("OPENDECK_BROKER_HOME", str(tmp_path))
    (tmp_path / "token").mkdir()  # make the token path a dir so read/write raises
    t = Config().token()
    assert len(t) == 32  # secrets.token_hex(16) -> 32 hex chars
    assert t
