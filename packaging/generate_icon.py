"""Regenerates packaging/icon.ico (and icon_256.png) from Mike's mark.

The mark is the nib — a fountain-pen nib angled like a mouse pointer, cream on
a warm terracotta tile — drawn from the very same shape the app paints at
runtime (ui/workspace/nib.py), so the taskbar, the Start menu, the shortcut
and the window's own mark can never drift apart.

Windows needs it as a real .ico (a PE resource baked into the .exe, seen
before Qt ever paints a pixel), which can't be drawn at runtime the way the
tray icon is. Re-run this whenever the mark changes:

    python packaging/generate_icon.py

It is checked in rather than regenerated on every build, so a build has one
fewer moving part and the icon in git is the icon that ships.
"""
from __future__ import annotations

import io
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

SIZES = [16, 24, 32, 48, 64, 128, 256]

TILE_TOP = "#D2703F"
TILE_BOTTOM = "#B5552C"
NIB = "#F6EFE3"
COLLAR = "#7A2F14"


def render(px: int):
    """The icon at px×px, as a QImage."""
    from PySide6.QtCore import QRectF, Qt
    from PySide6.QtGui import QColor, QImage, QLinearGradient, QPainter, QPainterPath

    from ui.workspace import nib

    img = QImage(px, px, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing, True)
    # the smallest sizes use the whole square — a rounded tile at 16px just
    # loses pixels to its corners
    inset = 0.0 if px <= 24 else px * 0.03
    radius = px * (0.20 if px <= 24 else 0.23)
    tile = QPainterPath()
    tile.addRoundedRect(QRectF(inset, inset, px - 2 * inset, px - 2 * inset), radius, radius)
    grad = QLinearGradient(0, 0, 0, px)
    grad.setColorAt(0, QColor(TILE_TOP))
    grad.setColorAt(1, QColor(TILE_BOTTOM))
    p.fillPath(tile, grad)
    scale = 0.78 if px <= 24 else 0.70
    nib.paint_centred(p, QRectF(0, 0, px, px), QColor(NIB),
                      QColor(COLLAR) if px >= 32 else None, scale=scale)
    p.end()
    return img


def _to_pil(img):
    from PIL import Image
    from PySide6.QtCore import QBuffer, QIODevice

    buf = QBuffer()
    buf.open(QIODevice.WriteOnly)
    img.save(buf, "PNG")
    return Image.open(io.BytesIO(bytes(buf.data()))).convert("RGBA")


def main() -> None:
    from PySide6.QtGui import QGuiApplication

    app = QGuiApplication.instance() or QGuiApplication(sys.argv)  # noqa: F841
    here = os.path.dirname(os.path.abspath(__file__))
    images = {px: _to_pil(render(px)) for px in SIZES}
    images[256].save(os.path.join(here, "icon_256.png"))
    images[256].save(os.path.join(here, "icon.ico"), sizes=[(s, s) for s in SIZES],
                     append_images=[images[s] for s in SIZES if s != 256])
    print("wrote icon.ico and icon_256.png")


if __name__ == "__main__":
    main()
