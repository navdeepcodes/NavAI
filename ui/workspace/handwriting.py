"""Handwriting — Mike's thoughts, written out by the nib, stroke by stroke.

Not a script font revealed behind a moving mask. The letters come from the
Hershey script: real pen strokes, in the order a hand makes them (public
domain; see ui/fonts/HERSHEY.txt). Each stroke is smoothed, then drawn over
time at a human pace — faster on straight runs, slower through curves, a lift
between strokes, a breath between words — with ink that swells and thins by
the direction of travel, the way a broad fountain-pen nib does, and that
lands slightly glossy before it dries to the page colour. The nib itself rides
the pen point the whole time.
"""
from __future__ import annotations

import json
import math
import os
import random
from functools import lru_cache

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPen

from ui.workspace import nib as _nib

#: Hershey units from the top of a capital to the baseline.
_CAP = 21.0
#: The broad-nib angle: strokes along it are hairlines, across it are full.
_NIB_EDGE = math.radians(40)


@lru_cache(maxsize=1)
def _font() -> dict:
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    import sys
    for base in (os.path.join(getattr(sys, "_MEIPASS", ""), "ui"), here):
        path = os.path.join(base, "fonts", "hershey_script.json")
        if base and os.path.isfile(path):
            with open(path, encoding="utf-8") as fh:
                return json.load(fh)
    return {"glyphs": {}}


def available() -> bool:
    return bool(_font().get("glyphs"))


def _smooth(points: list[tuple[float, float]], steps: int = 4) -> list[tuple[float, float]]:
    """Catmull-Rom through the Hershey vertices, so curves read as a hand's."""
    if len(points) < 3:
        return points
    out = []
    pts = [points[0]] + points + [points[-1]]
    for i in range(1, len(pts) - 2):
        p0, p1, p2, p3 = pts[i - 1], pts[i], pts[i + 1], pts[i + 2]
        for k in range(steps):
            t = k / steps
            t2, t3 = t * t, t * t * t
            x = 0.5 * ((2 * p1[0]) + (-p0[0] + p2[0]) * t
                       + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2
                       + (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3)
            y = 0.5 * ((2 * p1[1]) + (-p0[1] + p2[1]) * t
                       + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2
                       + (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3)
            out.append((x, y))
    out.append(points[-1])
    return out


class Script:
    """One line of handwriting, laid out and timed, ready to draw at any t."""

    #: pen speed, Hershey units per second (a relaxed, legible hand)
    SPEED = 150.0
    LIFT = 0.07          # seconds the pen is off the page between strokes
    WORD_GAP = 0.12      # a breath between words

    def __init__(self, text: str, seed: int | None = None) -> None:
        self.text = text
        rnd = random.Random(seed if seed is not None else hash(text))
        glyphs = _font().get("glyphs", {})
        segs: list[tuple[float, float, float, float, float, float]] = []
        # each segment: x0, y0, x1, y1, t_start, t_end
        pen_x = 0.0
        t = 0.0
        min_y, max_y = 0.0, 0.0
        for ch in text:
            g = glyphs.get(ch) or glyphs.get("?")
            if g is None:
                continue
            if ch == " ":
                t += self.WORD_GAP
            ox = pen_x - g["l"]
            # a hand never lands a letter in exactly the same place twice
            jy = rnd.uniform(-0.35, 0.35)
            for stroke in g["s"]:
                pts = _smooth([(x + ox, y + jy) for x, y in stroke])
                t += self.LIFT
                prev = None
                for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
                    d = math.hypot(x1 - x0, y1 - y0)
                    if d <= 1e-6:
                        continue
                    # a hand slows through tight turns and flies on the straights
                    ang = math.atan2(y1 - y0, x1 - x0)
                    turn = 0.0
                    if prev is not None:
                        turn = abs((ang - prev + math.pi) % (2 * math.pi) - math.pi) / math.pi
                    prev = ang
                    dt = d / self.SPEED * (1.0 + 1.4 * turn)
                    segs.append((x0, y0, x1, y1, t, t + dt))
                    t += dt
                    min_y, max_y = min(min_y, y0, y1), max(max_y, y0, y1)
            pen_x += g["w"]
        self.segments = segs
        self.duration = t
        self.width = pen_x
        self.top = min(min_y, -_CAP)
        self.bottom = max(max_y, 9.0)

    def pen_at(self, t: float) -> tuple[float, float, bool]:
        """Where the pen tip is at time t, and whether it's touching paper."""
        if not self.segments:
            return 0.0, 0.0, False
        for (x0, y0, x1, y1, a, b) in self.segments:
            if t < a:
                # in a lift: glide toward the next stroke's start
                return x0, y0 - 2.5, False
            if t <= b:
                f = (t - a) / (b - a) if b > a else 1.0
                return x0 + (x1 - x0) * f, y0 + (y1 - y0) * f, True
        x0, y0, x1, y1, a, b = self.segments[-1]
        return x1, y1, False

    def paint(self, p: QPainter, origin: QPointF, scale: float, t: float,
              ink: QColor, wet: QColor | None = None, opacity: float = 1.0,
              weight: float = 1.0) -> QPointF:
        """Draw the writing as it stands at time t; return the pen point.

        origin is the baseline start in widget pixels; scale is px per unit.
        """
        base_w = max(0.9, scale * 1.55) * weight
        pen = QPen()
        pen.setCapStyle(Qt.RoundCap)
        ox, oy = origin.x(), origin.y()
        for (x0, y0, x1, y1, a, b) in self.segments:
            if a > t:
                break
            f = 1.0 if t >= b else (t - a) / (b - a)
            ex, ey = x0 + (x1 - x0) * f, y0 + (y1 - y0) * f
            # broad-nib contrast: full across the nib edge, hairline along it
            ang = math.atan2(y1 - y0, x1 - x0)
            w = base_w * (0.45 + 0.75 * abs(math.sin(ang - _NIB_EDGE)))
            col = QColor(ink)
            if wet is not None:
                # fresh ink is glossy for a moment, then dries to the ink colour
                age = t - b if t >= b else 0.0
                k = max(0.0, 1.0 - age / 0.55)
                if k > 0:
                    col = QColor(
                        int(ink.red() + (wet.red() - ink.red()) * k),
                        int(ink.green() + (wet.green() - ink.green()) * k),
                        int(ink.blue() + (wet.blue() - ink.blue()) * k))
            col.setAlphaF(max(0.0, min(1.0, opacity)))
            pen.setColor(col)
            pen.setWidthF(w)
            p.setPen(pen)
            p.drawLine(QPointF(ox + x0 * scale, oy + y0 * scale),
                       QPointF(ox + ex * scale, oy + ey * scale))
        px, py, _down = self.pen_at(t)
        return QPointF(ox + px * scale, oy + py * scale)


def paint_pen(p: QPainter, tip: QPointF, size: float, colour: QColor,
              collar: QColor | None, down: bool, wobble: float = 0.0) -> None:
    """The nib at the pen point: pressed to the page while writing, lifted
    a touch between strokes."""
    lift = 0.0 if down else size * 0.08
    _nib.paint(p, QPointF(tip.x() + lift * 0.6, tip.y() - lift), size, colour,
               collar, _nib.ANGLE + wobble)
