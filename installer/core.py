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
    files = [p for p in source.rglob("*") if p.is_file()]
    total = max(1, len(files))
    if target.exists():
        shutil.rmtree(target, ignore_errors=True)
    target.mkdir(parents=True, exist_ok=True)
    for index, path in enumerate(files, 1):
        destination = target / path.relative_to(source)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)
        if index % 20 == 0 or index == total:
            on_progress(int(index / total * 100), f"Copying files… {index} of {total}")


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
