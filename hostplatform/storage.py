"""Where Mike's data actually lives, decided in exactly one place.

Before this module, the per-user data root
(`~/Library/Application Support/Mike`) was independently reconstructed in
eight files: config/preferences.py, and brain/memory_store.py,
revert_store.py, situation_store.py, activity_store.py, projects.py,
capability_probe.py, plus a ninth copy of the pattern in
voice/providers/qwen.py for the optional voice install. That is the same
second-hardcoded-copy shape this repo has already been bitten by twice
(a duplicate NUM_CTX, a duplicate OLLAMA_MODEL) — one fact, repeated, drifts.
It also meant nobody could add Windows support without editing eight files
identically and hoping none were missed.

Three other paths were worse than duplicated — they were never rooted here
at all, and instead resolved relative to the process's current working
directory: `logs/mike.log`, `audio/recordings/`, and `storage/token.json`
(the OAuth token — the single most sensitive file Mike holds, sitting next
to the source in plaintext, in whatever directory the app happened to be
launched from). All three now resolve here too.

`MIKE_DATA_DIR` overrides everything below for tests: tests/conftest.py and
tests/_isolate.py set it to a throwaway temp directory before any store is
imported, so a test run can never touch the real per-user data — including,
now, the voice install location, which did not respect the override before.
"""
from __future__ import annotations

import os
import platform
from pathlib import Path


def _override() -> Path | None:
    value = os.environ.get("MIKE_DATA_DIR", "").strip()
    return Path(value) if value else None


def data_dir() -> Path:
    """The root Mike's own data lives under. Created if missing.

    macOS:   ~/Library/Application Support/Mike
    Windows: %LOCALAPPDATA%\\Mike
    other:   $XDG_DATA_HOME/Mike, or ~/.local/share/Mike — Mike does not yet
             support computer control here, but data still needs somewhere
             honest to live rather than falling back to macOS's path by
             accident.
    """
    override = _override()
    if override is not None:
        root = override
    else:
        system = platform.system()
        if system == "Darwin":
            root = Path.home() / "Library" / "Application Support" / "Mike"
        elif system == "Windows":
            base = os.environ.get("LOCALAPPDATA")
            root = Path(base) / "Mike" if base else Path.home() / "AppData" / "Local" / "Mike"
        else:
            base = os.environ.get("XDG_DATA_HOME")
            root = Path(base) / "Mike" if base else Path.home() / ".local" / "share" / "Mike"
    root.mkdir(parents=True, exist_ok=True)
    return root


def db_path(name: str = "memory.db") -> Path:
    """A local SQLite database under the data root.

    All of Mike's stores share one file (`memory.db`) — separate tables, one
    connection, wrapped for thread-safety by brain/_local_db.py. This exists
    so every store asks for its path the same way rather than rebuilding it.
    """
    return data_dir() / name


def logs_dir() -> Path:
    path = data_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def log_path(name: str = "mike.log") -> Path:
    """Where Mike's own log file lives.

    Used to be `logs/mike.log`, relative to whatever directory the process
    was launched from. An installed app is frequently launched from a
    directory it cannot write to, and even when it can, that scattered a log
    file into whatever folder happened to be current at launch.
    """
    return logs_dir() / name


def cache_dir() -> Path:
    path = data_dir() / "cache"
    path.mkdir(parents=True, exist_ok=True)
    return path


def recordings_dir() -> Path:
    """Where the push-to-talk recorder writes its capture.

    Used to be `audio/recordings/`, relative to the working directory —
    the same class of bug as the log path.
    """
    path = data_dir() / "recordings"
    path.mkdir(parents=True, exist_ok=True)
    return path


def token_path() -> Path:
    """Where the Google OAuth token is stored.

    Used to be the literal string `"storage/token.json"` — relative to the
    working directory, and version-controllable by accident if that
    directory were ever added to git. It carries a live credential and
    belongs in the same per-user, per-machine location as everything else
    Mike keeps.
    """
    return data_dir() / "token.json"


def voice_home_candidates() -> list[Path]:
    """Where an optional local neural-voice installation might live, in the
    order they are checked.

    A storage-location decision, so it lives here rather than in
    voice/providers/qwen.py. `MIKE_VOICE_HOME` is a separate, narrower
    override from `MIKE_DATA_DIR` — set when only the voice install (not all
    of Mike's data) needs to point somewhere else. The first real
    installation was created by hand for a benchmark at `~/.mike-tts-bench`,
    and is kept as a fallback candidate so it still works; the primary
    location is under Mike's own data root, which — unlike the hardcoded
    path this replaces — now correctly respects `MIKE_DATA_DIR` under test
    isolation.
    """
    override = os.environ.get("MIKE_VOICE_HOME", "").strip()
    candidates = [Path(override)] if override else []
    candidates.append(data_dir() / "voice")
    candidates.append(Path.home() / ".mike-tts-bench")
    return candidates
