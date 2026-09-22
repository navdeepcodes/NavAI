"""Regenerates packaging/icon.ico from Mike's own mark.

Not a separate design decision — this is the exact glyph served as
huddlecode.com's favicon (verified by reading its <link rel="icon"> data URI
directly): a rounded dark square with three bars of the site's own --ink
background and --paper bar color, the same tokens ui/panel/style.py already
reads off that stylesheet. Windows needs the mark as a real .ico (a PE
resource baked into the .exe, seen before Qt ever paints a pixel — the
taskbar icon, the shortcut icon, the Explorer thumbnail), which can't be
drawn at runtime the way the tray dot is. Re-run this whenever the mark
changes; it is checked in as packaging/icon.ico rather than regenerated on
every build so a build has one fewer moving part and the icon a developer
sees in git is the icon that ships.
"""
from __future__ import annotations

import os

from PIL import Image, ImageDraw

INK = (13, 13, 12, 255)      # --ink, the site's background bar color
PAPER = (250, 249, 247, 255)  # --paper, the mark's own bars

# Source geometry: the 32x32 viewBox from huddlecode.com's favicon SVG.
SIZE = 32
CORNER_RADIUS = 6
BARS = [
    # (x, y, w, h) in the 32-unit source space, each with rx=1.5 (== w/2).
    (9, 13, 3, 6),
    (14.5, 8, 3, 16),
    (20, 11, 3, 10),
]

SUPERSAMPLE = 8  # rendered at 8x then downsampled for anti-aliasing


def render(px: int) -> Image.Image:
    scale = SUPERSAMPLE
    hi = px * scale
    unit = hi / SIZE

    img = Image.new("RGBA", (hi, hi), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle(
        [0, 0, hi - 1, hi - 1], radius=CORNER_RADIUS * unit, fill=INK,
    )
    for x, y, w, h in BARS:
        draw.rounded_rectangle(
            [x * unit, y * unit, (x + w) * unit, (y + h) * unit],
            radius=(w / 2) * unit,
            fill=PAPER,
        )
    return img.resize((px, px), Image.LANCZOS)


def main() -> None:
    sizes = [16, 24, 32, 48, 64, 128, 256]
    images = [render(s) for s in sizes]
    out_path = os.path.join(os.path.dirname(__file__), "icon.ico")
    images[-1].save(
        out_path, format="ICO", sizes=[(s, s) for s in sizes], append_images=images[:-1],
    )
    print(f"Wrote {out_path} ({os.path.getsize(out_path)} bytes)")

    png_path = os.path.join(os.path.dirname(__file__), "icon_256.png")
    images[-1].save(png_path, format="PNG")
    print(f"Wrote {png_path}")


if __name__ == "__main__":
    main()
