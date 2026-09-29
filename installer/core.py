"""Mike's installer, as a window rather than a console.

A zip is not an install. What a user actually got was: unzip, open a folder
full of DLLs, guess which file is the application, run it from their
Downloads folder, and end up with no Start Menu entry and nothing to
double-click tomorrow.

The first version of this fix was a PowerShell script, which is worse than
it sounds -- a black console box is exactly the "this is a developer tool"
tell that the rest of Mike's design works to avoid. So this is the same
work behind a real window, using the PySide6 that Mike already ships, in
the same visual language as the app itself.

It is reached by running Mike.exe from anywhere that isn't the install
location, which means the file a user instinctively double-clicks is the
right one. There is nothing else in the zip to be confused by.

Deliberately per-user (%LOCALAPPDATA%\\Programs\\Mike): no administrator, no
UAC prompt, so a student on a managed laptop can still install it.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

INSTALL_DIR = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Programs" / "Mike"
APP_NAME = "Mike"


def running_from_install_dir() -> bool:
    try:
        here = Path(sys.executable).resolve().parent
        return here == INSTALL_DIR.resolve()
    except Exception:
        return False


def already_installed() -> bool:
    return (INSTALL_DIR / "Mike.exe").is_file()


def source_dir() -> Path:
    """The unpacked Mike folder this executable is sitting in."""
    return Path(sys.executable).resolve().parent


# ── the work ────────────────────────────────────────────────

def copy_tree(source: Path, target: Path, on_progress) -> None:
    """Put the Mike in `source` at `target`, without ever leaving half of one.

    The first version deleted the old install (errors ignored) and copied over
    it. With Mike still running in the tray -- the normal state for anyone
    installing a newer zip -- the delete skipped every file in use and the copy
    then failed on the first of them: a broken install that no longer started.

    Now the new files are copied beside the old install first, then the two
    folders are swapped by renaming, and only then is the old one removed. A
    rename fails cleanly while anything inside is still in use, so it is
    retried for a while and, if it never succeeds, the old install is left
    exactly as it was.
    """
    files = [p for p in source.rglob("*") if p.is_file()]
    total = max(1, len(files))
    staging = target.with_name(target.name + ".new")
    retired = target.with_name(target.name + ".old")
    for leftover in (staging, retired):
        if leftover.exists():
            shutil.rmtree(leftover, ignore_errors=True)
    staging.mkdir(parents=True, exist_ok=True)
    for index, path in enumerate(files, 1):
        destination = staging / path.relative_to(source)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)
        if index % 20 == 0 or index == total:
            on_progress(int(index / total * 95), f"Copying files… {index} of {total}")

    if target.exists():
        on_progress(96, "Replacing the old version…")
        _rename_with_patience(target, retired)
    try:
        _rename_with_patience(staging, target)
    except Exception:
        if retired.exists() and not target.exists():
            retired.rename(target)            # put the old Mike back
        raise
    shutil.rmtree(retired, ignore_errors=True)


def _rename_with_patience(source: Path, target: Path, seconds: float = 30.0) -> None:
    """Rename, retrying while Windows still holds a file inside (a Mike that is
    shutting down, an antivirus scan of the new files)."""
    import time

    deadline = time.monotonic() + seconds
    while True:
        try:
            source.rename(target)
            return
        except OSError:
            if time.monotonic() >= deadline:
                raise OSError(
                    f"{source.name} is still in use -- close Mike and try again") from None
            time.sleep(0.5)


def clean_leftovers() -> None:
    """A folder an interrupted install or update left beside the install."""
    for suffix in (".new", ".old"):
        leftover = INSTALL_DIR.with_name(INSTALL_DIR.name + suffix)
        if leftover.exists():
            shutil.rmtree(leftover, ignore_errors=True)


# ── a Mike that is already running ──────────────────────────

def running_mike(folder: Path | None = None) -> list[int]:
    """Process ids of every program running from Mike's install folder (Mike
    himself, and anything launched from beside him)."""
    if sys.platform != "win32":
        return []
    import ctypes
    from ctypes import wintypes

    folder = (folder or INSTALL_DIR).resolve()

    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                    ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", ctypes.c_size_t),
                    ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                    ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", ctypes.c_long),
                    ("dwFlags", wintypes.DWORD), ("szExeFile", ctypes.c_wchar * 260)]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    snapshot = kernel32.CreateToolhelp32Snapshot(0x2, 0)          # TH32CS_SNAPPROCESS
    if snapshot in (None, wintypes.HANDLE(-1).value):
        return []
    pids = []
    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        more = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
        while more:
            pids.append(entry.th32ProcessID)
            more = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snapshot)

    mine, found = os.getpid(), []
    for pid in pids:
        if pid in (0, 4, mine):
            continue
        handle = kernel32.OpenProcess(0x1000, False, pid)   # QUERY_LIMITED_INFORMATION
        if not handle:
            continue
        try:
            buf = ctypes.create_unicode_buffer(1024)
            size = wintypes.DWORD(len(buf))
            if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
                try:
                    Path(buf.value).resolve().relative_to(folder)
                    found.append(pid)
                except ValueError:
                    pass
        finally:
            kernel32.CloseHandle(handle)
    return found


def wait_for_exit(pids: list[int], seconds: float) -> list[int]:
    """Wait for these processes to end; the ones still running after `seconds`."""
    import time

    deadline = time.monotonic() + seconds
    alive = list(pids)
    while alive and time.monotonic() < deadline:
        alive = [pid for pid in alive if _alive(pid)]
        if alive:
            time.sleep(0.25)
    return [pid for pid in alive if _alive(pid)]


def _alive(pid: int) -> bool:
    if sys.platform != "win32":
        return False
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    handle = kernel32.OpenProcess(0x1000 | 0x00100000, False, pid)   # + SYNCHRONIZE
    if not handle:
        return False
    try:
        return kernel32.WaitForSingleObject(handle, 0) == 0x102          # WAIT_TIMEOUT
    finally:
        kernel32.CloseHandle(handle)


def stop_running_mike(seconds: float = 10.0) -> bool:
    """End every program running from the install folder, so its files can be
    replaced. True when none is left."""
    pids = running_mike()
    if not pids:
        return True
    if sys.platform == "win32":
        import ctypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        for pid in pids:
            handle = kernel32.OpenProcess(0x0001, False, pid)          # PROCESS_TERMINATE
            if handle:
                kernel32.TerminateProcess(handle, 0)
                kernel32.CloseHandle(handle)
    return not wait_for_exit(pids, seconds)


def make_shortcuts(target: Path) -> None:
    """Start Menu and Desktop, via the Windows Script Host COM object.

    GetFolderPath rather than ~/Desktop on purpose: OneDrive redirects the
    Desktop on a great many Windows machines, and a shortcut written to the
    literal home path would simply never appear for those users.
    """
    exe = target / "Mike.exe"
    try:
        import win32com.client

        shell = win32com.client.Dispatch("WScript.Shell")
        start_menu = Path(shell.SpecialFolders("StartMenu")) / "Programs" / "Mike.lnk"
        desktop = Path(shell.SpecialFolders("Desktop")) / "Mike.lnk"
        for link in (start_menu, desktop):
            link.parent.mkdir(parents=True, exist_ok=True)
            shortcut = shell.CreateShortcut(str(link))
            shortcut.TargetPath = str(exe)
            shortcut.WorkingDirectory = str(target)
            shortcut.IconLocation = f"{exe},0"
            shortcut.Description = "Mike - a personal assistant that lives on your PC"
            shortcut.Save()
    except Exception:
        # A missing shortcut is a smaller failure than a failed install.
        pass


def ollama_present() -> bool:
    if shutil.which("ollama"):
        return True
    candidate = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe"
    return candidate.is_file()


def uninstall() -> None:
    """Remove Mike and its shortcuts. Leaves personal data alone.

    The awkward part is that this runs from inside the folder it has to
    delete: Windows holds a lock on a running executable, so a plain rmtree
    removes everything it can and silently leaves Mike.exe (and whatever is
    open beneath it) behind. Verified -- the first version reported success
    while leaving a working copy installed, which is worse than failing,
    because the user believes it is gone.

    So the directory removal is handed to a detached shell that waits for
    this process to exit first. `rmdir /s /q` on a path that no longer has a
    running binary inside it then succeeds.
    """
    try:
        import win32com.client

        shell = win32com.client.Dispatch("WScript.Shell")
        for link in (
            Path(shell.SpecialFolders("StartMenu")) / "Programs" / "Mike.lnk",
            Path(shell.SpecialFolders("Desktop")) / "Mike.lnk",
        ):
            if link.exists():
                link.unlink()
    except Exception:
        pass

    running_from_here = False
    try:
        running_from_here = Path(sys.executable).resolve().parent == INSTALL_DIR.resolve()
    except Exception:
        pass

    if not running_from_here:
        shutil.rmtree(INSTALL_DIR, ignore_errors=True)
        return

    # ping is the standard no-dependency way to sleep in a bare cmd line;
    # it gives this process time to exit and release the lock.
    subprocess.Popen(
        f'ping 127.0.0.1 -n 4 >nul & rmdir /s /q "{INSTALL_DIR}"',
        shell=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
        | getattr(subprocess, "DETACHED_PROCESS", 0),
    )
