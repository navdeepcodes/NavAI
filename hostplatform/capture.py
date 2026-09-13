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
        _capture_windows(path)
        return
    raise NotImplementedError(f"Screen capture is not implemented for {system}.")


def _capture_windows(path: str) -> None:
    """BitBlt of the primary display, deliberately not Windows.Graphics.
    Capture: this process is not DPI-aware (verified: GetProcessDpiAwareness
    returns 0), so GetSystemMetrics(SM_CXSCREEN/SM_CYSCREEN) already reports
    the same virtualized, non-physical resolution that computer.windows'
    click coordinates and UI Automation's bounding rectangles use — the same
    virtualization GDI honors automatically for an unaware caller. Capturing
    at that size, not the physical panel resolution, is what keeps a
    screenshot and a click landing in the same coordinate space on a scaled
    display; verified directly on a 200%-scaled machine, not assumed.
    """
    import ctypes

    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32

    width = user32.GetSystemMetrics(0)   # SM_CXSCREEN
    height = user32.GetSystemMetrics(1)  # SM_CYSCREEN
    if width <= 0 or height <= 0:
        raise CaptureError(f"GetSystemMetrics reported an unusable screen size ({width}x{height}).")

    screen_dc = user32.GetDC(0)
    if not screen_dc:
        raise CaptureError("GetDC(0) failed — no display device context available.")
    mem_dc = gdi32.CreateCompatibleDC(screen_dc)
    bitmap = gdi32.CreateCompatibleBitmap(screen_dc, width, height)
    try:
        old = gdi32.SelectObject(mem_dc, bitmap)
        SRCCOPY = 0x00CC0020
        if not gdi32.BitBlt(mem_dc, 0, 0, width, height, screen_dc, 0, 0, SRCCOPY):
            raise CaptureError("BitBlt failed.")
        gdi32.SelectObject(mem_dc, old)

        from PIL import Image

        class _BITMAPINFOHEADER(ctypes.Structure):
            _fields_ = [
                ("biSize", ctypes.c_uint32), ("biWidth", ctypes.c_int32),
                ("biHeight", ctypes.c_int32), ("biPlanes", ctypes.c_uint16),
                ("biBitCount", ctypes.c_uint16), ("biCompression", ctypes.c_uint32),
                ("biSizeImage", ctypes.c_uint32), ("biXPelsPerMeter", ctypes.c_int32),
                ("biYPelsPerMeter", ctypes.c_int32), ("biClrUsed", ctypes.c_uint32),
                ("biClrImportant", ctypes.c_uint32),
            ]

        header = _BITMAPINFOHEADER()
        header.biSize = ctypes.sizeof(_BITMAPINFOHEADER)
        header.biWidth = width
        header.biHeight = -height   # negative: top-down, matches screen order
        header.biPlanes = 1
        header.biBitCount = 32
        header.biCompression = 0    # BI_RGB

        buffer_size = width * height * 4
        buf = ctypes.create_string_buffer(buffer_size)
        got = gdi32.GetDIBits(mem_dc, bitmap, 0, height, buf,
                              ctypes.byref(header), 0)  # DIB_RGB_COLORS
        if not got:
            raise CaptureError("GetDIBits failed.")

        img = Image.frombuffer("RGB", (width, height), buf, "raw", "BGRX", 0, 1)
        img.save(path)
    finally:
        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(mem_dc)
        user32.ReleaseDC(0, screen_dc)


def capture_to_tempfile(suffix: str = "_raw.png", *, timeout: float | None = None) -> str:
    """Same as `capture_to_file`, into a fresh temp path that is returned."""
    path = tempfile.mktemp(suffix=suffix)
    capture_to_file(path, timeout=timeout)
    return path
