"""A tool call's arguments while they're still arriving.

The model writes a tool call's arguments as JSON, a few characters at a time.
For write_files that's the whole content of every file -- many seconds, on a
laptop -- and "Thinking…" for all of them reads as stuck. What's complete so
far is worth knowing before the end (which file is being written now), and
only what's complete: half a path is not a path.

Each character is looked at once, as it arrives: re-reading the whole text at
every piece would be quadratic in a 20KB call. value() is what the text so far
means, cut back to the last value that was finished, with its brackets closed.
"""
from __future__ import annotations

import json

_CLOSE = {"{": "}", "[": "]"}
_SPACE = " \t\r\n"


class PartialJSON:
    def __init__(self) -> None:
        self._parts: list[str] = []
        self._n = 0                     # characters read
        self._stack: list[str] = []     # the open { and [
        self._in_string = False
        self._escaped = False
        self._string_is_key = False
        self._expect_key = False        # in an object, before its next key
        self._in_scalar = False         # a number, true, false or null
        self._cut = 0                   # the text up to here is whole values
        self._cut_stack: tuple[str, ...] = ()
        #: Values finished so far -- it changes exactly when value() does.
        self.values = 0

    def feed(self, chunk: str) -> None:
        for ch in chunk:
            self._step(ch)
            self._n += 1
        self._parts.append(chunk)

    def _whole(self, at: int) -> None:
        self._cut, self._cut_stack = at, tuple(self._stack)

    def _step(self, ch: str) -> None:
        at = self._n
        if self._in_string:
            if self._escaped:
                self._escaped = False
            elif ch == "\\":
                self._escaped = True
            elif ch == '"':
                self._in_string = False
                if not self._string_is_key:
                    self.values += 1
                    self._whole(at + 1)
            return
        if self._in_scalar and (ch in ",}]" or ch in _SPACE):
            self._in_scalar = False
            self.values += 1
            self._whole(at)
        if ch == '"':
            self._in_string = True
            self._string_is_key = bool(self._stack) and self._stack[-1] == "{" and self._expect_key
        elif ch in _CLOSE:
            self._stack.append(ch)
            self._expect_key = ch == "{"
            self._whole(at + 1)
        elif ch in "}]":
            if self._stack:
                self._stack.pop()
            self._expect_key = False
            self.values += 1
            self._whole(at + 1)
        elif ch == ":":
            self._expect_key = False
        elif ch == ",":
            self._expect_key = bool(self._stack) and self._stack[-1] == "{"
        elif ch not in _SPACE:
            self._in_scalar = True

    def value(self):
        """What's whole so far, or None when nothing is yet."""
        if self._cut == 0:
            return None
        text = "".join(self._parts)[: self._cut]
        text += "".join(_CLOSE[c] for c in reversed(self._cut_stack))
        try:
            return json.loads(text)
        except ValueError:
            return None
