"""
Draw the app icon (an original pirate chest illustration) and write:
    src/fortnite_chest_counter/gui/assets/icon_<size>.png   window / taskbar icon used by the desktop app
    packaging/launcher/app.ico                               icon of "Fortnite Visual Chest Counter.exe"
Developers only (needs Pillow):   python packaging/make_icon.py
The outputs are committed, so a release build does not need Pillow.
"""

import shutil
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
S = 1024                                            # drawing size; every output is a high-quality downscale


def lerp(a, b, t):
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def draw():
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))

    # tile: rounded square with a vertical gradient
    grad = Image.new("RGBA", (S, S))
    gd = ImageDraw.Draw(grad)
    for y in range(S):
        gd.line([(0, y), (S, y)], fill=lerp((73, 45, 31), (28, 24, 20), y / S) + (255,))
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([24, 24, S - 24, S - 24], radius=210, fill=255)
    img.paste(grad, (0, 0), mask)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([24, 24, S - 24, S - 24], radius=210, outline=(168, 121, 79, 160), width=10)

    # soft glow behind the chest
    glow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse([210, 250, 814, 860], fill=(251, 191, 36, 70))
    img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(70)))
    d = ImageDraw.Draw(img)

    wood, wood_dark, gold, gold_dark = (200, 128, 40), (110, 64, 16), (250, 208, 100), (170, 120, 30)
    x0, x1 = 190, 834
    lid_top, lid_bottom, body_bottom = 290, 520, 812

    # body
    d.rounded_rectangle([x0, lid_bottom - 10, x1, body_bottom], radius=46, fill=wood, outline=wood_dark, width=22)
    # lid (rounded top)
    d.rounded_rectangle([x0, lid_top, x1, lid_bottom + 30], radius=150, fill=lerp(wood, (255, 255, 255), 0.08),
                        outline=wood_dark, width=22)
    d.rectangle([x0 + 11, lid_bottom - 6, x1 - 11, lid_bottom + 30], fill=wood)
    # rim between lid and body
    d.rounded_rectangle([x0 - 14, lid_bottom - 26, x1 + 14, lid_bottom + 26], radius=22, fill=gold, outline=gold_dark, width=12)
    # metal bands
    for bx in (318, 662):
        d.rounded_rectangle([bx - 34, lid_top + 22, bx + 34, body_bottom - 4], radius=18, fill=gold, outline=gold_dark, width=10)
    # Gold chain and gems identify the normal pirate chest even at small sizes.
    for x, y in ((316, 595), (370, 563), (654, 563), (708, 595)):
        d.rounded_rectangle([x - 39, y - 17, x + 39, y + 17], radius=17, outline=gold, width=16)
    for x in (318, 706):
        d.ellipse([x - 44, 305, x + 44, 385], fill=(220, 95, 250), outline=(68, 34, 70), width=12)

    # Skull clasp with gem eyes and a dark keyhole.
    skull = [(416, 444), (608, 444), (646, 530), (584, 598), (574, 640), (450, 640),
             (440, 598), (378, 530)]
    d.polygon(skull, fill=(231, 228, 217), outline=(50, 33, 27), width=14)
    for x in (457, 567):
        d.ellipse([x - 29, 480, x + 29, 538], fill=(220, 95, 250), outline=(68, 34, 70), width=10)
    d.ellipse([495, 540, 529, 574], fill=(49, 28, 24))
    d.polygon([(501, 564), (523, 564), (531, 601), (493, 601)], fill=(49, 28, 24))

    # sparkle
    cx, cy, r = 790, 230, 70
    d.polygon([(cx, cy - r), (cx + 16, cy - 16), (cx + r, cy), (cx + 16, cy + 16), (cx, cy + r), (cx - 16, cy + 16),
               (cx - r, cy), (cx - 16, cy - 16)], fill=(255, 250, 230))
    return img


def main():
    big = draw()
    assets = ROOT / "src" / "fortnite_chest_counter" / "gui" / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    sizes = [16, 24, 32, 48, 64, 128, 256]
    for size in sizes:
        big.resize((size, size), Image.LANCZOS).save(assets / f"icon_{size}.png", optimize=True)
    ico = ROOT / "packaging" / "launcher" / "app.ico"
    ico.parent.mkdir(parents=True, exist_ok=True)
    big.resize((256, 256), Image.LANCZOS).save(ico, sizes=[(s, s) for s in sizes])
    shutil.copy2(ico, assets / "app.ico")       # the app's Windows window-class icon (gui/app.py set_class_icon)
    print(f"wrote {assets} and {ico}")


if __name__ == "__main__":
    main()
