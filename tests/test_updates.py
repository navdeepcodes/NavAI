"""Updates: finding a newer Mike, fetching it safely, and swapping it in
without ever leaving a broken install (installer/updates.py, installer/core.py,
ui/workspace/updater.py)."""
from __future__ import annotations

import hashlib
import http.server
import io
import json
import os
import sys
import threading
import zipfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests import _isolate  # noqa: F401

import pytest

from installer import core, updates


# ── choosing a release ─────────────────────────────────────────

def _release(tag, assets, draft=False, pre=False, body="## Notes\nFaster PDFs."):
    return {"tag_name": tag, "draft": draft, "prerelease": pre, "body": body,
            "html_url": f"https://example/{tag}", "assets": assets}


def _asset(name, size=10, digest="sha256:" + "a" * 64):
    return {"name": name, "size": size, "digest": digest,
            "browser_download_url": f"https://example/{name}"}


def test_the_newest_windows_build_is_chosen_and_nothing_else():
    releases = [
        _release("v1.0.0", [_asset("Mike-windows-1.0.0.zip"), _asset("Mike-macOS-1.0.0.zip")]),
        _release("v1.2.0", [_asset("Mike-windows-1.2.0.zip")]),
        _release("v1.1.0", [_asset("Mike-windows-1.1.0.zip")]),
        _release("v9.0.0", [_asset("Mike-windows-9.0.0.zip")], draft=True),
        _release("v8.0.0", [_asset("Mike-windows-8.0.0.zip")], pre=True),
        _release("v7.0.0", [_asset("Mike-macOS-7.0.0.zip")]),
    ]
    found = updates.newest(releases, "1.1.0")
    assert found is not None and found.version == "1.2.0"
    assert found.sha256 == "a" * 64
    assert found.headline == "Faster PDFs."          # not the "## Notes" heading
    assert updates.newest(releases, "1.2.0") is None
    assert updates.newest(releases, "1.10.0") is None  # 1.10 > 1.2, not string order


def test_versions_compare_as_numbers():
    assert updates.version_tuple("v1.10.0") > updates.version_tuple("1.9.9")
    assert updates.version_tuple("1.1") < updates.version_tuple("1.1.1")
    assert updates.version_tuple("nonsense") == (0,)


# ── downloading ────────────────────────────────────────────────

def _zip(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return buf.getvalue()


class _Server:
    """A stand-in for GitHub: serves whatever bytes each path is given."""

    def __init__(self, routes: dict[str, bytes]) -> None:
        routes_ = routes

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                body = routes_.get(self.path)
                if body is None:
                    self.send_response(404)
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass

        self.httpd = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.httpd.server_port}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()


@pytest.fixture
def server():
    made = []

    def make(routes):
        s = _Server(routes)
        made.append(s)
        return s
    yield make
    for s in made:
        s.close()


def _offer(url, data, sha=None):
    return updates.Update(version="9.9.9", url=url, size=len(data),
                          sha256=sha if sha is not None else hashlib.sha256(data).hexdigest(),
                          notes="", page="")


def test_a_verified_download_is_unpacked_to_its_mike_exe(server):
    data = _zip({"Mike/Mike.exe": b"new mike", "Mike/_internal/x.dll": b"lib"})
    s = server({"/Mike-windows-9.9.9.zip": data})
    seen = []
    exe = updates.download(_offer(f"{s.url}/Mike-windows-9.9.9.zip", data),
                           on_progress=lambda d, t: seen.append((d, t)))
    assert exe.read_bytes() == b"new mike"
    assert seen and seen[-1] == (len(data), len(data))
    assert not list(updates.updates_dir().glob("*.zip*"))   # the archive is gone


def test_a_download_that_doesnt_match_the_published_file_is_refused(server):
    data = _zip({"Mike/Mike.exe": b"tampered"})
    s = server({"/m.zip": data})
    with pytest.raises(IOError, match="doesn't match"):
        updates.download(_offer(f"{s.url}/m.zip", data, sha="0" * 64))
    assert not (updates.updates_dir() / "9.9.9").exists()


def test_a_zip_that_writes_outside_its_folder_is_refused(server):
    data = _zip({"../../evil.txt": b"x", "Mike/Mike.exe": b"m"})
    s = server({"/m.zip": data})
    with pytest.raises(IOError, match="unsafe"):
        updates.download(_offer(f"{s.url}/m.zip", data))


def test_check_reads_the_feed(server, monkeypatch):
    data = json.dumps([_release("v99.0.0", [_asset("Mike-windows-99.0.0.zip")])]).encode()
    s = server({"/releases": data})
    monkeypatch.setenv("MIKE_UPDATE_FEED", f"{s.url}/releases")
    found = updates.check()
    assert found is not None and found.version == "99.0.0"


# ── swapping the install folder ────────────────────────────────

def _tree(root: Path, files: dict[str, str]) -> None:
    for name, text in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text)


def test_an_install_replaces_the_old_version_completely(tmp_path):
    old, new = tmp_path / "Mike", tmp_path / "src"
    _tree(old, {"Mike.exe": "old", "gone.dll": "old only"})
    _tree(new, {"Mike.exe": "new", "_internal/a.dll": "a"})
    core.copy_tree(new, old, lambda p, m: None)
    assert (old / "Mike.exe").read_text() == "new"
    assert (old / "_internal/a.dll").exists()
    assert not (old / "gone.dll").exists()
    assert not (tmp_path / "Mike.new").exists() and not (tmp_path / "Mike.old").exists()


def test_a_failed_swap_keeps_the_old_version(tmp_path, monkeypatch):
    old, new = tmp_path / "Mike", tmp_path / "src"
    _tree(old, {"Mike.exe": "old"})
    _tree(new, {"Mike.exe": "new"})
    real = core._rename_with_patience

    def flaky(src, dst, seconds=30.0):
        if src.name == "Mike.new":
            raise OSError("in use")
        return real(src, dst, seconds)

    monkeypatch.setattr(core, "_rename_with_patience", flaky)
    with pytest.raises(OSError):
        core.copy_tree(new, old, lambda p, m: None)
    assert (old / "Mike.exe").read_text() == "old"


@pytest.mark.skipif(sys.platform != "win32", reason="Windows file locking")
def test_a_file_in_use_leaves_the_old_install_untouched(tmp_path, monkeypatch):
    """What used to break installs: Mike still running from the folder."""
    import ctypes
    from ctypes import wintypes

    old, new = tmp_path / "Mike", tmp_path / "src"
    _tree(old, {"Mike.exe": "old"})
    _tree(new, {"Mike.exe": "new"})
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateFileW.restype = wintypes.HANDLE
    kernel32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                     wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD,
                                     wintypes.HANDLE]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    # Opened the way a running program's own image is: no sharing for delete.
    handle = kernel32.CreateFileW(str(old / "Mike.exe"), 0x80000000, 0x1, None, 3, 0, None)
    real = core._rename_with_patience
    monkeypatch.setattr(core, "_rename_with_patience",
                        lambda s, d, seconds=30.0: real(s, d, 1.0))
    try:
        with pytest.raises(OSError, match="in use"):
            core.copy_tree(new, old, lambda p, m: None)
    finally:
        kernel32.CloseHandle(handle)
    assert (old / "Mike.exe").read_text() == "old"


@pytest.mark.skipif(sys.platform != "win32", reason="Windows processes")
def test_running_programs_are_found_by_their_folder(tmp_path):
    import subprocess

    here = Path(sys.executable).resolve().parent
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        assert child.pid in core.running_mike(here)
        assert child.pid not in core.running_mike(tmp_path)
    finally:
        child.kill()
        child.wait()
    assert core.wait_for_exit([child.pid], 2) == []


# ── in the app ─────────────────────────────────────────────────

def _qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication(sys.argv)


def _wait_for(predicate, seconds=10.0):
    import time
    from PySide6.QtWidgets import QApplication
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        QApplication.processEvents()
        if predicate():
            return True
        time.sleep(0.02)
    return False


def test_the_app_offers_a_newer_version_in_the_chat(server, monkeypatch):
    _qapp()
    from ui.workspace.chat_page import _UpdateBanner
    from ui.workspace.updater import Updater

    body = json.dumps([_release("v99.0.0", [_asset("Mike-windows-99.0.0.zip")],
                                body="Sharper voice and quicker PDFs.")]).encode()
    s = server({"/releases": body})
    monkeypatch.setenv("MIKE_UPDATE_FEED", f"{s.url}/releases")
    updater = Updater()
    banner = _UpdateBanner()
    updater.available.connect(banner.offer)
    updater.check(manual=True)
    assert _wait_for(lambda: updater.offer is not None)
    assert _wait_for(lambda: not banner.isHidden())
    assert "99.0.0" in banner._title.text()
    assert "quicker PDFs" in banner._detail.text()
    assert "99.0.0" in updater.last_status


def test_up_to_date_is_said_plainly(server, monkeypatch):
    _qapp()
    from ui.workspace.updater import Updater

    s = server({"/releases": json.dumps([]).encode()})
    monkeypatch.setenv("MIKE_UPDATE_FEED", f"{s.url}/releases")
    updater = Updater()
    updater.check(manual=True)
    assert _wait_for(lambda: "up to date" in updater.last_status)
    assert updater.offer is None


def test_the_automatic_check_respects_the_setting(monkeypatch):
    _qapp()
    from config import preferences
    from ui.workspace.updater import Updater

    preferences.set_value("check_updates", False)
    try:
        called = []
        monkeypatch.setattr(updates, "check", lambda: called.append(1))
        Updater().check(manual=False)
        _wait_for(lambda: bool(called), 0.5)
        assert not called
    finally:
        preferences.set_value("check_updates", True)


def test_after_an_update_mike_says_so_once():
    _qapp()
    from config import preferences
    from config.settings import VERSION
    from ui.workspace.updater import Updater

    preferences.set_value("last_run_version", "0.0.1")
    said = []
    u = Updater()
    u.updated.connect(said.append)
    u.start()
    assert _wait_for(lambda: said == [VERSION], 4)
    said.clear()
    again = Updater()
    again.updated.connect(said.append)
    again.start()                        # next launch: nothing to say
    _wait_for(lambda: bool(said), 2)
    assert not said


def test_updating_is_refused_outside_an_installed_build():
    _qapp()
    from ui.workspace.updater import Updater

    u = Updater()
    u._offer = updates.Update("9.9.9", "u", 1, "", "", "")
    failed = []
    u.failed.connect(failed.append)
    u.install()
    assert failed and "installed Mike" in failed[0]


# ── the installer window itself ────────────────────────────────

def test_the_installer_window_builds_for_install_and_for_update(monkeypatch):
    """main.py imports installer.window only in a packaged build, so nothing
    else in the suite ever loaded it -- a syntax error in it shipped as
    "No module named 'installer.window'" on every launch of the zip."""
    _qapp()
    from installer import window

    # never start a real install from a test
    monkeypatch.setattr(window.InstallerWindow, "_install", lambda self: None)
    monkeypatch.setattr(core, "running_mike", lambda folder=None: [1234])
    fresh = window.InstallerWindow()
    assert fresh._go.text() == "Close Mike and install"
    assert "closes him first" in fresh._body.text()
    updating = window.InstallerWindow(update_from=4321)
    assert updating.windowTitle() == "Updating Mike"
    assert "updating to" in updating._body.text()
    assert "\n\n" in updating._body.text()
    fresh.close()
    updating.close()
