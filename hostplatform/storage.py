"""Where Mike's on-disk state lives, per platform.

macOS keeps the traditional ~/Library layout. Linux follows the XDG base
directory spec (falling back to the spec's own defaults when the env vars
aren't set, same as every other well-behaved Linux app). Every directory is
created on first access so callers never have to think about it.
"""
from __future__ import annotations

import os
from pathlib import Path

from hostplatform import current_platform

APP_NAME = "Mike"


def _xdg(env_var: str, default_relative: str) -> Path:
    value = os.environ.get(env_var)
    if value:
        return Path(value)
    return Path.home() / default_relative


def _ensure(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def data_dir() -> Path:
    """Long-lived state: memory db, credentials, preferences.

    Holds credentials and personal memory, so it's kept user-only
    (0700) rather than inheriting the umask-default 0755.
    """
    system = current_platform()
    if system == "Darwin":
        d = Path.home() / "Library" / "Application Support" / APP_NAME
    elif system == "Linux":
        d = _xdg("XDG_DATA_HOME", ".local/share") / APP_NAME
    else:
        d = Path.home() / f".{APP_NAME.lower()}"
    _ensure(d)
    try:
        d.chmod(0o700)
    except OSError:
        pass
    return d


def cache_dir() -> Path:
    """Disposable state: recordings, screenshot temp files."""
    system = current_platform()
    if system == "Darwin":
        d = Path.home() / "Library" / "Caches" / APP_NAME
    elif system == "Linux":
        d = _xdg("XDG_CACHE_HOME", ".cache") / APP_NAME
    else:
        d = data_dir() / "cache"
    return _ensure(d)


def log_dir() -> Path:
    system = current_platform()
    if system == "Darwin":
        d = Path.home() / "Library" / "Logs" / APP_NAME
    elif system == "Linux":
        d = _xdg("XDG_STATE_HOME", ".local/state") / APP_NAME / "logs"
    else:
        d = data_dir() / "logs"
    return _ensure(d)


def recordings_dir() -> Path:
    return _ensure(cache_dir() / "recordings")


def memory_db_path() -> Path:
    """Single sqlite file shared by memory/activity/situation stores."""
    return data_dir() / "memory.db"


def preferences_path() -> Path:
    return data_dir() / "preferences.json"
