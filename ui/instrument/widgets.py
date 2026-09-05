"""Small instrument fixtures: an LED, a trip counter, and the two text
registers — engraved labels / machine ticker on the dark side, and the
logbook's ink-on-paper prose on the light side.
"""
from __future__ import annotations

from html import escape

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QWidget

from ui.instrument import tokens


class LED(QWidget):
    """A single indicator light. Off unless there's something real to say."""

    def __init__(self, diameter: int = 7, parent=None) -> None:
        super().__init__(parent)
        self._d = diameter
        self._on = None
        self.setFixedSize(diameter, diameter)

    def set(self, colour: str | None) -> None:
        """colour: None (off), or one of tokens.AMBER/RED/GREEN."""
        self._on = colour
        self.setStyleSheet(self._css())

    def _css(self) -> str:
        if not self._on:
            return (
                f"background: #2E2820; border-radius: {self._d // 2}px;"
            )
        return (
            f"background: {self._on}; border-radius: {self._d // 2}px;"
            f"border: 0; "
        )

    def paintEvent(self, event) -> None:
        from PySide6.QtGui import QPainter, QColor, QRadialGradient
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        if self._on:
            glow = QRadialGradient(self._d / 2, self._d / 2, self._d * 1.4)
            c = QColor(self._on)
            c.setAlphaF(0.55)
            glow.setColorAt(0, c)
            glow.setColorAt(1, QColor(0, 0, 0, 0))
            painter.setPen(Qt.NoPen)
            painter.setBrush(glow)
            painter.drawEllipse(self.rect().adjusted(-int(self._d), -int(self._d), int(self._d), int(self._d)))
            painter.setBrush(QColor(self._on))
        else:
            painter.setBrush(QColor(tokens.HAIRLINE))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(0, 0, self._d, self._d)


class Counter(QLabel):
    """
    An honest trip counter. Ticks once per real completed action — never a
    percentage, never a total, because Mike genuinely cannot know how many
    steps remain.
    """

    def __init__(self, value: int = 0, parent=None) -> None:
        super().__init__(parent)
        self.setFont(tokens.machine(12))
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet(
            f"background: #0F0D0A; color: {tokens.AMBER};"
            f"border: 1px solid #38322A; border-radius: 3px;"
            f"padding: 3px 8px;"
        )
        self.set_value(value)

    def set_value(self, value: int) -> None:
        self.setText(f"{value:02d}")


class EngravedLabel(QLabel):
    """A panel label — small, condensed, uppercase, quiet."""

    def __init__(self, text: str = "", colour: str | None = None, size: int = 10, parent=None) -> None:
        super().__init__(parent)
        self._colour = colour or tokens.MUTED
        self._size = size
        self.setFont(tokens.label(size))
        self.setStyleSheet("background: transparent; border: none;")
        self.set_text(text)

    def set_text(self, text: str) -> None:
        self.setText(text.upper())
        self.setStyleSheet(
            f"background: transparent; border: none; color: {self._colour};"
        )

    def set_colour(self, colour: str) -> None:
        self._colour = colour
        self.setStyleSheet(
            f"background: transparent; border: none; color: {colour};"
        )


class MachineTicker(QLabel):
    """What Mike observed or did — mono, on the dark side."""

    def __init__(self, text: str = "", size: int = 12, colour: str | None = None, parent=None):
        super().__init__(parent)
        self._size = size
        self._colour = colour or tokens.MUTED
        self.setStyleSheet("background: transparent; border: none;")
        self.set_text(text)

    def set_text(self, text: str) -> None:
        self._raw = text
        self.setTextFormat(Qt.RichText)
        self.setWordWrap(True)
        self.setText(
            f'<div style="line-height:168%; color:{self._colour}; '
            f'font-family:{tokens.mono_family()}; font-size:{self._size}px;">'
            f'{escape(text).replace(chr(10), "<br>")}</div>'
        )

    def set_colour(self, colour: str) -> None:
        self._colour = colour
        self.set_text(getattr(self, "_raw", ""))


# ══ Logbook — the paper side ═══════════════════════════════

class LogbookPage(QFrame):
    """The paper window set into the dark housing. Ruled lines, warm cream."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setStyleSheet(
            f"""
            QFrame {{
                background: {tokens.PAPER};
                border-radius: 6px;
            }}
            """
        )


class Ink(QLabel):
    """What Mike (or the user) actually said — warm serif, dark ink on paper."""

    def __init__(self, text: str = "", size: int = 15, parent=None) -> None:
        super().__init__(parent)
        self.setStyleSheet("background: transparent; border: none;")
        self._size = size
        self.set_text(text)

    def set_text(self, text: str) -> None:
        self._raw = text
        self.setTextFormat(Qt.RichText)
        self.setWordWrap(True)
        self.setText(
            f'<div style="line-height:150%; color:{tokens.INK}; '
            f'font-family:{tokens.serif_family()}; font-size:{self._size}px;">'
            f'{escape(text).replace(chr(10), "<br>")}</div>'
        )

    def append_text(self, chunk: str) -> None:
        self.set_text(getattr(self, "_raw", "") + chunk)

    def raw(self) -> str:
        return getattr(self, "_raw", "")


class InkFact(QLabel):
    """A machine fact inside the logbook — mono, muted, still on paper."""

    def __init__(self, text: str = "", parent=None) -> None:
        super().__init__(parent)
        self.setStyleSheet("background: transparent; border: none;")
        self.setTextFormat(Qt.RichText)
        self.setWordWrap(True)
        self.set_text(text)

    def set_text(self, text: str) -> None:
        self.setText(
            f'<div style="line-height:160%; color:{tokens.INK_DIM}; '
            f'font-family:{tokens.mono_family()}; font-size:11.5px;">'
            f'{escape(text).replace(chr(10), "<br>")}</div>'
        )


class Byline(QLabel):
    """YOU / MIKE — a small hand-marker at the top of each logbook entry."""

    def __init__(self, who: str, parent=None) -> None:
        super().__init__(parent)
        colour = tokens.INK_ACCENT if who.lower() == "mike" else "#A99A7C"
        self.setStyleSheet(
            f"background: transparent; border: none; color: {colour};"
        )
        font = tokens.label(9.5)
        self.setFont(font)
        self.setText(who.upper())
