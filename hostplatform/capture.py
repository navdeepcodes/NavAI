"""Screen capture, per platform.

macOS: the `screencapture` CLI — always available, no permission dance
beyond the one-time Screen Recording grant macOS itself prompts for.

Linux: there is no single API that works everywhere. X11 has direct
frame-grab tools; Wayland compositors (GNOME, KDE, ...) deliberately block
that and require going through the xdg-desktop-portal Screenshot interface,
which is the only mechanism that works across compositors without picking a
specific one. That portal call shows the user a one-time system permission
dialog (by design — a sandboxed/background process should not be able to
grab the screen silently) and blocks until they respond, so callers get a
clear TimeoutError rather than a silent hang or a fake image if nobody
answers it in time.
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from hostplatform import current_platform

# How long we wait for the user to respond to the one-time portal
# permission dialog (or for an already-granted request to complete).
PORTAL_TIMEOUT_SECONDS = 20.0


class CaptureUnavailable(RuntimeError):
    """Raised when this platform/session cannot produce a screenshot."""


def capture_raw() -> Path:
    """Capture the full screen and return the path to a saved PNG.

    Caller owns the returned file and is responsible for deleting it.
    """
    system = current_platform()

    if system == "Darwin":
        return _capture_macos()

    if system == "Linux":
        return _capture_linux_portal()

    raise NotImplementedError(f"Screen capture is not implemented on {system}.")


def _capture_macos() -> Path:
    out = Path(tempfile.mktemp(suffix="_raw.png"))
    subprocess.run(["screencapture", "-x", str(out)], check=True)
    return out


def _capture_linux_portal() -> Path:
    try:
        import gi

        gi.require_version("GLib", "2.0")
        gi.require_version("Gio", "2.0")
        from gi.repository import Gio, GLib
    except (ImportError, ValueError) as exc:
        raise CaptureUnavailable(
            "Screen capture needs PyGObject (gi) for the xdg-desktop-portal "
            "D-Bus call, and it isn't importable in this environment."
        ) from exc

    connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)

    result: dict = {"uri": None, "error": None, "done": False}
    loop = GLib.MainLoop()

    def on_response(_conn, _sender, _path, _iface, _signal, params, *_a):
        code, values = params.unpack()
        if code == 0:
            result["uri"] = values.get("uri")
        else:
            result["error"] = f"Portal screenshot request was not granted (code {code})."
        result["done"] = True
        loop.quit()

    proxy = Gio.DBusProxy.new_sync(
        connection,
        Gio.DBusProxyFlags.NONE,
        None,
        "org.freedesktop.portal.Desktop",
        "/org/freedesktop/portal/desktop",
        "org.freedesktop.portal.Screenshot",
        None,
    )

    request_handle = proxy.call_sync(
        "Screenshot",
        GLib.Variant("(sa{sv})", ("", {"interactive": GLib.Variant("b", False)})),
        Gio.DBusCallFlags.NONE,
        -1,
        None,
    )
    request_path = request_handle.unpack()[0]

    connection.signal_subscribe(
        "org.freedesktop.portal.Desktop",
        "org.freedesktop.portal.Request",
        "Response",
        request_path,
        None,
        Gio.DBusSignalFlags.NONE,
        on_response,
    )

    def on_timeout():
        if not result["done"]:
            result["error"] = (
                "Timed out waiting for the screenshot portal. On Wayland this call shows a "
                "one-time system permission dialog — it needs a human to click Allow/Share "
                "in an interactive session before automated captures will work."
            )
            loop.quit()
        return False

    GLib.timeout_add_seconds(int(PORTAL_TIMEOUT_SECONDS), on_timeout)
    loop.run()

    if result["error"] or not result["uri"]:
        raise CaptureUnavailable(result["error"] or "Screenshot portal returned no image.")

    uri = result["uri"]
    path = Path(uri[len("file://"):]) if uri.startswith("file://") else Path(uri)
    if not path.exists():
        raise CaptureUnavailable(f"Portal reported a screenshot at {path} but the file is missing.")
    return path


def is_available() -> bool:
    """Best-effort check of whether capture can plausibly work here.

    On Linux this only confirms the portal is reachable, not that a human
    will be present to approve the permission dialog.
    """
    system = current_platform()
    if system == "Darwin":
        return shutil.which("screencapture") is not None
    if system == "Linux":
        try:
            import gi  # noqa: F401
        except ImportError:
            return False
        return True
    return False
