"""Your data, yours to take and yours to erase.

Export writes one zip of everything Mike keeps about you — chats, memory,
activity, preferences — as readable JSON, so it can be kept, inspected or
moved. Erase functions remove each kind, or everything at once (Reset).
"""
from __future__ import annotations

import json
import time
import zipfile
from pathlib import Path

from logs.logger import logger

_README = """Mike — your data export
Created: {when}

chats.json        every saved conversation, with each message you and Mike wrote
memory.json       what Mike remembers about you
activity.json     what Mike did on your computer (files, apps, commands)
preferences.json  your settings
account.json      your Mike account, if you're signed in: email, name, photo path
                  (never your password or sign-in token)

Everything here came from this computer; nothing was fetched from a server.
"""


def export_zip(path: str | Path) -> Path:
    from brain import activity_store, conversation_store, memory_store
    from config import preferences

    path = Path(path)
    try:
        memories = memory_store.all_memories(limit=100000)
    except Exception:
        memories = []
    parts = {
        "chats.json": conversation_store.export_all(),
        "memory.json": memories,
        "activity.json": activity_store.recent(limit=100000),
        "preferences.json": preferences.all_values(),
    }
    try:
        from account import session_store
        profile = session_store.load_profile()
        if profile:
            parts["account.json"] = {k: profile.get(k) for k in
                                     ("email", "display_name", "avatar_path", "user_id")}
    except Exception:
        logger.debug("No account to export.", exc_info=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("README.txt", _README.format(when=time.strftime("%Y-%m-%d %H:%M")))
        for name, data in parts.items():
            zf.writestr(name, json.dumps(data, indent=2, ensure_ascii=False, default=str))
    logger.info("Exported data to %s", path)
    return path


def delete_all_chats() -> None:
    from brain import conversation_store
    conversation_store.delete_all()


def clear_activity() -> None:
    from brain import activity_store
    activity_store.clear()


def forget_memory() -> None:
    from brain import memory_store
    memory_store.forget(query="everything")


def reset_everything() -> None:
    """Chats, memory, activity and settings — back to a fresh install."""
    delete_all_chats()
    clear_activity()
    try:
        forget_memory()
    except Exception:
        logger.exception("Could not clear memory during reset.")
    from config import preferences
    try:
        Path(preferences.path()).unlink(missing_ok=True)
        preferences._cache = None           # reload defaults on next read
    except Exception:
        logger.exception("Could not reset preferences.")
    try:
        from hostplatform import autostart
        autostart.set_enabled(False)
    except Exception:
        pass
    _erase_traces()


def _erase_traces() -> None:
    """Logs, the crash log, the last voice recording, the Mike account sign-in
    and the Gmail sign-in — everything the Privacy Policy says Reset removes."""
    try:
        from account import session_store
        session_store.clear()
    except Exception:
        logger.exception("Could not remove the account sign-in during reset.")
    import logging
    from logging.handlers import RotatingFileHandler
    from hostplatform import storage

    # the live log file is held open by its handler: empty it in place
    for h in logging.getLogger().handlers:
        if isinstance(h, RotatingFileHandler) and h.stream is not None:
            try:
                h.acquire()
                h.stream.seek(0)
                h.stream.truncate()
            except Exception:
                pass
            finally:
                h.release()
    logs = storage.log_path().parent
    for old in logs.glob("mike.log.*"):
        try:
            old.unlink()
        except Exception:
            pass
    try:
        from ui.system import lifecycle
        if lifecycle._crash_file is not None:
            lifecycle._crash_file.seek(0)
            lifecycle._crash_file.truncate()
    except Exception:
        pass
    for path in (storage.recordings_dir() / "voice_input.wav", storage.token_path()):
        try:
            path.unlink(missing_ok=True)
        except Exception:
            logger.exception("Could not remove %s during reset.", path)
