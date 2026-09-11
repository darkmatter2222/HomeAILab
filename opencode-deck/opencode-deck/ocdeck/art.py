"""Original procedural artwork. No downloaded assets or image-generation dependency."""
import math
from functools import lru_cache
from PIL import Image, ImageDraw, ImageFont

PALETTE = {"running": (32, 235, 117), "idle": (255, 179, 46),
           "input": (255, 55, 75), "ready": (50, 204, 255), "unknown": (255, 179, 46)}
LABELS = {"running": "RUNNING", "idle": "IDLE", "input": "INPUT", "ready": "READY", "unknown": "LINK ?"}


@lru_cache(maxsize=1024)
def frame(state, label, slot, phase, size=80):
    image = Image.new("RGB", (size, size), "black")
    if state == "off":
        return image
    # Draw at 2x for smooth curves, then downsample. Discrete phases bound cache size.
    scale = size / 80
    im = Image.new("RGB", (160, 160), (3, 6, 10))
    d = ImageDraw.Draw(im)
    color = PALETTE[state]
    t = phase / 24 * 2 * math.pi
    pulse = (1 + math.sin(t)) / 2
    power = 0.45 + 0.55 * pulse if state == "input" else 0.55 + 0.25 * pulse
    c = tuple(int(x * power) for x in color)
    d.rounded_rectangle((3, 3, 156, 156), radius=22, fill=tuple(int(x * .08) for x in c), outline=c, width=3)
    if state == "running":
        d.ellipse((48, 23, 112, 87), outline=tuple(int(x * .2) for x in color), width=5)
        d.arc((48, 23, 112, 87), phase * 15, phase * 15 + 110, fill=color, width=6)
        d.polygon([(74, 42), (74, 69), (94, 55)], fill=color)
    elif state == "input":
        radius = 22 + int(pulse * 8)
        d.ellipse((80-radius, 54-radius, 80+radius, 54+radius), fill=c)
        d.rounded_rectangle((77, 35, 83, 57), radius=2, fill=(15, 2, 3))
        d.ellipse((77, 63, 83, 69), fill=(15, 2, 3))
    elif state == "ready":
        d.arc((47, 21, 113, 87), phase*15, phase*15+270, fill=c, width=3)
        d.line([(64, 53), (76, 65), (98, 41)], fill=color, width=6)
    elif state == "idle":
        d.rounded_rectangle((62, 36, 71, 73), radius=3, fill=c)
        d.rounded_rectangle((89, 36, 98, 73), radius=3, fill=c)
    else:
        d.line([(64, 36), (96, 68)], fill=color, width=5)
        d.line([(96, 36), (64, 68)], fill=color, width=5)
    # Pillow's bundled font keeps the ZIP self-contained and handles ASCII consistently.
    font = ImageFont.load_default(size=17)
    small = ImageFont.load_default(size=13)
    d.text((80, 101), LABELS[state], fill=color, font=font, anchor="mm")
    title = "DEVICE ONLINE" if state == "ready" else f"{slot+1}  {label[:13]}"
    title = title.encode("ascii", "replace").decode()
    d.text((80, 130), title, fill=(210, 219, 228), font=small, anchor="mm")
    return im.resize((size, size), Image.Resampling.LANCZOS)
