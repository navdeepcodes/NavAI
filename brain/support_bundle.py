"""Report a problem — a diagnostics file the user creates, inspects and sends.

Nothing is uploaded. This writes one zip on the user's computer with what's
needed to understand a problem: Mike's version, the system, whether the brain
and voice are working, the settings (without the user's name or "about me"),
and Mike's logs. The logs can contain parts of what was asked — the app says
so before creating the file, and the file can be opened and read before it's
sent anywhere.
"""
from __future__ import annotations

import json
import platform
import sys
import time
import zipfile
from pathlib import Path

from logs.logger import logger

#: Preferences never included in a report — they're about the person, not the bug.
_PRIVATE_PREFS = {"profile_name", "profile_about"}


def system_summary() -> dict:
    from config import settings
    info: dict = {
        "mike_version": settings.VERSION,
        "created": time.strftime("%Y-%m-%d %H:%M:%S %z"),
        "os": f"{platform.system()} {platform.release()} ({platform.version()})",
        "machine": platform.machine(),
        "python": sys.version.split()[0],
        "frozen": bool(getattr(sys, "frozen", False)),
    }
    try:
        import PySide6
        from PySide6.QtCore import qVersion
        info["qt"] = f"PySide6 {PySide6.__version__} / Qt {qVersion()}"
    except Exception:
        pass
    try:
        from brain.diagnostics import check_brain
        b = check_brain()
        info["brain"] = {k: b.get(k) for k in ("provider", "model", "reachable",
                                               "model_pulled", "detail")}
    except Exception as exc:
        info["brain"] = f"check failed: {exc}"
    try:
        from dataclasses import asdict, is_dataclass
        from brain import hardware
        machine = hardware.current()
        info["hardware"] = asdict(machine) if is_dataclass(machine) else str(machine)
    except Exception:
        pass
    try:
        from brain import permissions
        info["permissions_off"] = sorted(permissions.disabled())
    except Exception:
        pass
    return info


def create(path: str | Path) -> Path:
    from config import preferences
    from hostplatform import storage

    path = Path(path)
    prefs = {k: v for k, v in preferences.all_values().items() if k not in _PRIVATE_PREFS}
    logs_dir = storage.log_path().parent
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("system.json", json.dumps(system_summary(), indent=2, default=str))
        zf.writestr("settings.json", json.dumps(prefs, indent=2, default=str))
        for log in sorted(logs_dir.glob("*.log*")):
            try:
                zf.write(log, arcname=f"logs/{log.name}")
            except Exception:
                logger.debug("Could not add %s to the report.", log, exc_info=True)
        zf.writestr("README.txt",
                    "Mike problem report\n\n"
                    "system.json   version, system and whether Mike's brain is working\n"
                    "settings.json your settings (your name and 'about you' are left out)\n"
                    "logs/         Mike's technical logs — these can include parts of\n"
                    "              what you asked Mike, file names and commands\n\n"
                    "Nothing was sent anywhere. Share this file only if you choose to.\n")
    logger.info("Created a problem report at %s", path)
    return path
