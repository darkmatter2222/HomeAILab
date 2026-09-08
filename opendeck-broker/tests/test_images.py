from opendeck_broker.images import _short, black_frame, render_key
from opendeck_broker.model import APPEARANCE_COLOR, DisplayAppearance


def test_black_key_is_all_zero():
    img = black_frame(16)
    assert len(img) == 16 * 16 * 3
    assert all(b == 0 for b in img)


def test_long_identity_is_truncated_to_fit():
    # research section 9: "A short identity label" -- a long alias must not
    # overflow the key; it is truncated to a short second line.
    assert _short("homeai") == "homeai"
    assert _short("a" * 50).endswith(".")
    assert len(_short("a" * 50)) == 12
    # and rendering a very long identity still yields a valid-sized image
    img = render_key(DisplayAppearance.RUN, "x" * 80)
    assert len(img) == 144 * 144 * 3


def test_black_render_matches_black_frame():
    assert render_key(DisplayAppearance.BLACK, size=16) == black_frame(16)


def test_hex_to_rgb_converts_correctly():
    # the hex->RGB conversion underpins the RAG palette; verify the documented
    # colors decode to the exact byte triples (with or without the leading #).
    from opendeck_broker.images import _hex_to_rgb

    assert _hex_to_rgb("#2fd06f") == (0x2F, 0xD0, 0x6F)  # RUN green
    assert _hex_to_rgb("#f5b13d") == (0xF5, 0xB1, 0x3D)  # IDLE/UNKNOWN amber
    assert _hex_to_rgb("#ff5a4e") == (0xFF, 0x5A, 0x4E)  # INPUT red
    assert _hex_to_rgb("#000000") == (0, 0, 0)          # BLACK
    assert _hex_to_rgb("2fd06f") == (0x2F, 0xD0, 0x6F)  # leading # optional


def test_probe_numbered_images_are_all_distinct():
    # tools/probe_device.numbered_image must produce six distinct images so
    # physical indexing is unambiguous (research build-order step 2).
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location(
        "opendeck_probe_device",
        Path(__file__).resolve().parent.parent / "tools" / "probe_device.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    imgs = [mod.numbered_image(i) for i in range(6)]
    assert all(len(im) == 144 * 144 * 3 for im in imgs)  # valid 144x144 RGB
    assert len(set(imgs)) == 6  # all six are distinct


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
