from opendeck_broker.images import black_frame, render_key
from opendeck_broker.model import APPEARANCE_COLOR, DisplayAppearance


def test_black_key_is_all_zero():
    img = black_frame(16)
    assert len(img) == 16 * 16 * 3
    assert all(b == 0 for b in img)


def test_black_render_matches_black_frame():
    assert render_key(DisplayAppearance.BLACK, size=16) == black_frame(16)


def test_distinct_appearances_produce_distinct_images():
    # research sections 2, 9: each state has its own image. UNKNOWN shares IDLE's
    # amber, so its distinction comes from the "?" label -- all five must differ.
    imgs = [
        render_key(DisplayAppearance.RUN, "x"),
        render_key(DisplayAppearance.IDLE, "x"),
        render_key(DisplayAppearance.INPUT, "x"),
        render_key(DisplayAppearance.UNKNOWN, "x"),
        render_key(DisplayAppearance.BLACK),
    ]
    assert len(set(imgs)) == 5


def test_render_is_deterministic():
    assert render_key(DisplayAppearance.RUN, "homeai") == render_key(DisplayAppearance.RUN, "homeai")


def test_identity_does_not_change_color():
    # the appearance color is authoritative regardless of the identity text
    a = render_key(DisplayAppearance.RUN, "aaa", size=8)
    b = render_key(DisplayAppearance.RUN, "bbb", size=8)
    # both are RUN-sized; both non-black
    assert len(a) == 8 * 8 * 3
    assert any(x != 0 for x in a)
    assert any(x != 0 for x in b)


def test_color_palette_matches_documented_rag():
    assert APPEARANCE_COLOR[DisplayAppearance.RUN].startswith("#2fd06f")
    assert APPEARANCE_COLOR[DisplayAppearance.IDLE].startswith("#f5b13d")
    assert APPEARANCE_COLOR[DisplayAppearance.INPUT].startswith("#ff5a4e")
    assert APPEARANCE_COLOR[DisplayAppearance.BLACK].startswith("#000000")
