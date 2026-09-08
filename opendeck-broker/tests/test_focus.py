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
