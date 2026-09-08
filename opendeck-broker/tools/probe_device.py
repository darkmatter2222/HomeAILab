"""Physical probe: prove Mini ownership + 6 black + 6 numbered + 6 key events.

This is build-order step 2 and the "click each of six keys" acceptance evidence.
It is PHYSICAL: it must run with the Mini attached and disabled in the Elgato
app. A green exit code here is hardware evidence, not a simulated API pass.

Usage:
  python tools/probe_device.py                 # open the Mini, black, numbered, then wait for presses
  python tools/probe_device.py --serial XXX
  python tools/probe_device.py --timeout 60    # seconds to wait for presses
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from opendeck_broker.device.hid_mini import ELGATO_VENDOR_ID, MINI_PRODUCT_IDS, ElgatoMiniHID  # noqa: E402
from opendeck_broker.images import render_key  # noqa: E402
from opendeck_broker.model import DisplayAppearance  # noqa: E402


def enumerate_elgato():
    import hid

    out = []
    for vid, pid in ((ELGATO_VENDOR_ID, p) for p in MINI_PRODUCT_IDS):
        for dev in hid.enumerate(vid, pid):
            out.append(dev)
    return out


def numbered_image(slot: int) -> bytes:
    # a distinct, bright image per slot so physical indexing is unambiguous
    colors = [
        (255, 0, 0), (0, 255, 0), (0, 0, 255),
        (255, 255, 0), (255, 0, 255), (0, 255, 255),
    ]
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (144, 144), colors[slot % 6])
    d = ImageDraw.Draw(img)
    try:
        from PIL import ImageFont

        font = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 60)
    except Exception:
        font = None
    d.text((50, 40), str(slot), fill=(255, 255, 255), font=font)
    return img.tobytes()


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--serial", default=None)
    p.add_argument("--timeout", type=float, default=60.0)
    args = p.parse_args()

    print("== opendeck-broker device probe (physical) ==")
    devs = enumerate_elgato()
    if not devs:
        print(f"FAIL: no Elgato Mini (vendor 0x{ELGATO_VENDOR_ID:04X}, product {MINI_PRODUCT_IDS}) found over HID.")
        print("     Is the Mini attached and disabled under Elgato > Preferences > Devices > Enabled?")
        return 1
    for d in devs:
        print(f"  candidate: product=0x{d['product_id']:04X} serial={d.get('serial_number')}")

    deck = ElgatoMiniHID(serial=args.serial)
    if not deck.connect():
        print("FAIL: could not open the Mini (app may still own it, or wrong product id).")
        return 1
    print(f"PASS: opened Mini via {deck.name}")

    # 1) six black
    for i in range(6):
        deck.set_key_image(i, render_key(DisplayAppearance.BLACK))
    print("PASS: uploaded six black images -- confirm the Mini is fully black.")
    time.sleep(1.0)

    # 2) six distinct numbered images (verify physical indexing)
    for i in range(6):
        deck.set_key_image(i, numbered_image(i))
    print("PASS: uploaded six numbered images 0..5 (row-major).")
    print("     Confirm the on-hardware numbering matches this row-major order.")
    time.sleep(1.0)

    # 3) capture six physical key events
    seen = set()

    def on_key(slot: int) -> None:
        seen.add(slot)
        print(f"  press edge: slot {slot}")

    deck.set_key_press_handler(on_key)
    print(f"Waiting up to {args.timeout:.0f}s for you to press all six keys...")
    deadline = time.time() + args.timeout
    # raw-hid reader: poll for key reports (the library path is event-driven)
    while len(seen) < 6 and time.time() < deadline:
        if deck._hid is not None:
            try:
                data = deck._hid.read(64)
                if data:
                    # Mini key report: the key index is carried in the report;
                    # validated layout is recorded here on first real run.
                    idx = data[0] if data and data[0] < 6 else None
                    if idx is not None:
                        on_key(idx)
            except Exception as e:  # noqa: BLE001
                print("  read error:", e)
        time.sleep(0.02)

    if seen == set(range(6)):
        print("PASS: received all six physical key events (one edge each).")
    else:
        print(f"PARTIAL: received presses for slots {sorted(seen)}; expected all six.")

    deck.close()
    return 0 if seen == set(range(6)) else 2


if __name__ == "__main__":
    raise SystemExit(main())
