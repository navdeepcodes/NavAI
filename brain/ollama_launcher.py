"""Finding and starting the local model runtime (Ollama) for the user.

The single most common first-run failure is simply that Ollama isn't
running — installed, but not started since the last reboot. Rather than
telling someone to open a terminal, Mike can start it: the Ollama desktop app
(which runs the server and lives in the tray) if it's installed, or the
`ollama serve` command otherwise.
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
from pathlib import Path

from logs.logger import logger

DOWNLOAD_URL = "https://ollama.com/download"


def _windows_candidates() -> list[Path]:
    local = os.environ.get("LOCALAPPDATA", "")
    progs = [os.environ.get("ProgramFiles", r"C:\Program Files"),
             os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")]
    out = []
    if local:
        out.append(Path(local) / "Programs" / "Ollama" / "ollama app.exe")
        out.append(Path(local) / "Programs" / "Ollama" / "ollama.exe")
    for p in progs:
        if p:
            out.append(Path(p) / "Ollama" / "ollama app.exe")
            out.append(Path(p) / "Ollama" / "ollama.exe")
    return out


def find() -> Path | None:
    """The Ollama executable to start, preferring the desktop app on Windows."""
    if platform.system() == "Windows":
        for path in _windows_candidates():
            if path.is_file():
                return path
    exe = shutil.which("ollama")
    return Path(exe) if exe else None


def installed() -> bool:
    return find() is not None


def start() -> bool:
    """Start Ollama in the background. True if a process was launched."""
    exe = find()
    if exe is None:
        return False
    try:
        args = [str(exe)] if exe.name.lower() == "ollama app.exe" else [str(exe), "serve"]
        kwargs: dict = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL,
                        "stdin": subprocess.DEVNULL}
        if platform.system() == "Windows":
            kwargs["creationflags"] = 0x00000008 | 0x08000000   # DETACHED | NO_WINDOW
        else:
            kwargs["start_new_session"] = True
        subprocess.Popen(args, **kwargs)
        logger.info("Started Ollama: %s", " ".join(args))
        return True
    except Exception:
        logger.exception("Could not start Ollama.")
        return False
