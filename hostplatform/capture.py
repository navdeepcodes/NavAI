"""Screen capture, kept separate from the vision model that consumes it.

Phase 10 of the Windows-transition audit: the vision model receives an image
path and must not know or care how it was acquired. `vision/screenshot.py`
used to *be* the macOS implementation — a bare `subprocess.run(["screencapture",
...])` with no seam between "take a screenshot" and "how this OS does that".
This module is that seam.

Windows is deliberately unimplemented rather than approximated. The correct
mechanism (Windows.Graphics.Capture, with a BitBlt/PrintWindow fallback for
older systems) has to be paired with DPI-aware coordinates — a screenshot
whose pixels don't line up with the coordinate space `computer.windows`
clicks in is worse than no screenshot, because it fails silently at the
click, not at the capture. See Phase 4 (DPI) of the audit.
"""
from __future__ import annotations

import platform
import subprocess
import tempfile


class CaptureError(RuntimeError):
    """The screen could not be captured."""


def capture_to_file(path: str, *, timeout: float | None = None) -> None:
    """Write a screenshot of the primary display to `path` (a .png).

    `timeout` bounds the capture — worth setting in an automated context,
    since `screencapture` can hang waiting on a screen-recording permission
    dialog rather than failing outright.
    """
    system = platform.system()
    if system == "Darwin":
        result = subprocess.run(
            ["screencapture", "-x", path], capture_output=True, timeout=timeout)
        if result.returncode != 0:
            message = (result.stderr or b"").decode(errors="replace").strip()
            raise CaptureError(message or "screencapture failed")
        return
    if system == "Windows":
        raise NotImplementedError(
            "Screen capture is not implemented for Windows yet. It needs "
            "Windows.Graphics.Capture (or a BitBlt/PrintWindow fallback) "
            "paired with DPI-aware coordinates, verified on the physical "
            "machine — a capture whose pixels don't match the coordinate "
            "space computer.windows clicks in would fail silently rather "
            "than loudly, which is worse than an honest gap."
        )
    raise NotImplementedError(f"Screen capture is not implemented for {system}.")


def capture_to_tempfile(suffix: str = "_raw.png", *, timeout: float | None = None) -> str:
    """Same as `capture_to_file`, into a fresh temp path that is returned."""
    path = tempfile.mktemp(suffix=suffix)
    capture_to_file(path, timeout=timeout)
    return path
