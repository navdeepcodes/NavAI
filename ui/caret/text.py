"""The two registers.

The whole honesty mechanism of this direction is typographic: prose is what
Mike *said*, mono behind a rule is what Mike *observed or did*. A reader can
tell a claim from a fact without reading a word, which matters for a model
that sometimes narrates an action instead of taking it.

Nothing here may be used for the other register's content.
"""
from __future__ import annotations

from html import escape

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel

from ui.caret import tokens


def _rich(label: QLabel, html: str) -> None:
    label.setTextFormat(Qt.RichText)
    label.setText(html)
    label.setWordWrap(True)
    label.setTextInteractionFlags(Qt.TextSelectableByMouse)
    label.setAttribute(Qt.WA_TranslucentBackground)


class Prose(QLabel):
    """What Mike said. System face, generous leading, reads as writing."""

    def __init__(self, text: str = "", size: int = 16, colour: str | None = None, parent=None):
        super().__init__(parent)
        self._size = size
        self._colour = colour or tokens.TEXT
        self.setStyleSheet("background: transparent; border: none;")
        self.set_text(text)

    def set_text(self, text: str) -> None:
        self._raw = text
        _rich(
            self,
            f'<div style="line-height:152%; color:{self._colour}; '
            f'font-family:{tokens.SANS}; font-size:{self._size}px; '
            f'letter-spacing:-0.1px;">{escape(text).replace(chr(10), "<br>")}</div>',
        )

    def append_text(self, chunk: str) -> None:
        self.set_text(self._raw + chunk)

    def raw(self) -> str:
        return self._raw


class Machine(QLabel):
    """What Mike observed or did. Mono, tighter, quieter than prose."""

    def __init__(
        self,
        text: str = "",
        size: int = 12,
        colour: str | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self._size = size
        self._colour = colour or tokens.MUTED
        self.setStyleSheet("background: transparent; border: none;")
        self.set_text(text)

    def set_text(self, text: str) -> None:
        self._raw = text
        _rich(
            self,
            f'<div style="line-height:168%; color:{self._colour}; '
            f'font-family:{tokens.mono_family()}; font-size:{self._size}px;">'
            f'{escape(text).replace(chr(10), "<br>")}</div>',
        )

    def set_colour(self, colour: str) -> None:
        self._colour = colour
        self.set_text(self._raw)

    def text_value(self) -> str:
        return self._raw
