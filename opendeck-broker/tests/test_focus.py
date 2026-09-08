from opendeck_broker.focus.windows import FocusStatus, WindowsFocusAdapter


def make_adapter(windows, foreground_after=None):
    """windows: list of (hwnd, title). foreground_after: hwnd the fake
    GetForegroundWindow returns after a focus attempt."""

    def enumerate(cb):
        for hwnd, title in windows:
            if not cb(hwnd, title):
                break

    def set_foreground(hwnd):
        return True

    def get_foreground():
        return foreground_after

    return WindowsFocusAdapter(
        enumerate_windows=enumerate,
        show_window=lambda hwnd, cmd=9: True,
        set_foreground=set_foreground,
        get_foreground=get_foreground,
    )


def test_not_found():
    ad = make_adapter([(10, "other window")])
    res = ad.focus_marker("opencode:homeai")
    assert res.status is FocusStatus.NOT_FOUND


def test_ambiguous_when_multiple_match():
    ad = make_adapter([(10, "[opencode:x] a"), (11, "[opencode:x] b")])
    res = ad.focus_marker("opencode:x")
    assert res.status is FocusStatus.AMBIGUOUS


def test_success_when_foreground_confirmed():
    ad = make_adapter([(10, "[opencode:homeai] opencode")], foreground_after=10)
    res = ad.focus_marker("opencode:homeai")
    assert res.status is FocusStatus.SUCCESS
    assert res.hwnd == 10
    assert res.observed_foreground == 10


def test_focus_denied_when_foreground_not_our_window():
    # We requested 10 but the OS reports 99 is foreground -> not proven focus.
    ad = make_adapter([(10, "[opencode:homeai] opencode")], foreground_after=99)
    res = ad.focus_marker("opencode:homeai")
    assert res.status is FocusStatus.FOCUS_DENIED_OR_WRONG_TARGET
    assert res.observed_foreground == 99


def test_marker_match_is_case_insensitive_substring():
    ad = make_adapter([(7, "HomeAILab - [opencode:HomeAI] opencode")], foreground_after=7)
    res = ad.focus_marker("opencode:homeai")
    assert res.status is FocusStatus.SUCCESS
    assert res.hwnd == 7


def test_focus_restores_window_before_foreground():
    # research section 10: "if target is minimized: restore it" then activate.
    from opendeck_broker.focus.windows import SW_RESTORE, WindowsFocusAdapter

    show_calls = []
    fg_calls = []

    def enumerate(cb):
        if not cb(42, "[opencode:x] w"):
            return

    ad = WindowsFocusAdapter(
        enumerate_windows=enumerate,
        show_window=lambda hwnd, cmd=9: (show_calls.append((hwnd, cmd)), True)[1],
        set_foreground=lambda hwnd: (fg_calls.append(hwnd), True)[1],
        get_foreground=lambda: 42,
    )
    res = ad.focus(42)
    assert res.status is FocusStatus.SUCCESS
    # restore (SW_RESTORE=9) is attempted on the target, then foreground
    assert (42, SW_RESTORE) in show_calls
    assert fg_calls == [42]
    # restore happens before the foreground request
    assert show_calls[0][0] == 42


def test_launch_project_uses_given_marker(monkeypatch):
    from opendeck_broker.focus.windows import launch_project

    calls = []

    class FakePopen:
        def __init__(self, args, **kw):
            calls.append(args)

    monkeypatch.setattr("opendeck_broker.focus.windows.subprocess.Popen", FakePopen)
    m = launch_project("/d/x", "bat.exe", "homeai", marker="opencode:homeai-a1b2c3")
    assert m == "opencode:homeai-a1b2c3"
    args = calls[0]
    assert args[0] == "wt"
    assert "-w" in args and "new" in args
    assert "-d" in args and "/d/x" in args
    # research section 10: a stable unique title the running TUI can't overwrite
    assert "--title" in args
    assert args[args.index("--title") + 1] == "opencode:homeai-a1b2c3"
    assert "--suppressApplicationTitle" in args
    # runs the launcher bat inside that dedicated window
    assert "bat.exe" in args


def test_launch_project_default_marker_is_unique(monkeypatch):
    import re

    from opendeck_broker.focus.windows import launch_project

    monkeypatch.setattr("opendeck_broker.focus.windows.subprocess.Popen", lambda *a, **k: None)
    m1 = launch_project("/d/x", "bat.exe", "homeai")
    m2 = launch_project("/d/x", "bat.exe", "homeai")
    # exact launch-token shape: opencode:<alias>-<6 hex chars>
    assert re.fullmatch(r"opencode:homeai-[0-9a-f]{6}", m1)
    assert m1 != m2  # two launches in the same dir get distinct tokens
