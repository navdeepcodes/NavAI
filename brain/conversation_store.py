"""Conversations — what was actually said, kept so Mike can be reopened and
continued.

Mike's working memory of a conversation (MikeCore.history) lives in RAM and
used to vanish on quit, so "close Mike, reopen, carry on" was impossible and
the History surface could only show an action log. This stores the visible
conversation — each user message and Mike's final reply, plus the running
situation summary — so a chat can be listed, reopened, and continued with the
same context.

Only the conversation a person saw is stored: final replies, not streamed
fragments, tool plumbing, or per-turn system snapshots. That is also what gets
restored into history, which keeps a reopened chat's prompt small.

Same local database and locking discipline as activity_store.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from typing import Any

from hostplatform import storage
from logs.logger import logger

_DB_DIR = storage.data_dir()
_DB_PATH = _DB_DIR / "memory.db"

#: A title is the first thing the user said, trimmed to something a list row
#: can hold.
TITLE_CHARS = 60


def _connect() -> sqlite3.Connection:
    _DB_DIR.mkdir(parents=True, exist_ok=True)
    from brain._local_db import connect as _locked_connect
    conn = _locked_connect(str(_DB_PATH))
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS conversations (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            title      TEXT    NOT NULL DEFAULT '',
            summary    TEXT    NOT NULL DEFAULT '',
            created_at REAL    NOT NULL,
            updated_at REAL    NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS conversation_messages (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL,
            role            TEXT    NOT NULL,
            content         TEXT    NOT NULL,
            attachments     TEXT    NOT NULL DEFAULT '',
            created_at      REAL    NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_conv_msgs "
        "ON conversation_messages(conversation_id, id)"
    )
    conn.commit()
    return conn


_conn: sqlite3.Connection | None = None
_conn_lock = threading.Lock()


def _db() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        with _conn_lock:
            if _conn is None:
                _conn = _connect()
    return _conn


def _title_from(text: str) -> str:
    line = " ".join((text or "").split())
    if len(line) <= TITLE_CHARS:
        return line
    cut = line[:TITLE_CHARS].rsplit(" ", 1)[0]
    return (cut or line[:TITLE_CHARS]) + "…"


def create() -> int | None:
    try:
        now = time.time()
        cur = _db().execute(
            "INSERT INTO conversations (title, summary, created_at, updated_at) "
            "VALUES ('', '', ?, ?)", (now, now),
        )
        _db().commit()
        return int(cur.lastrowid)
    except Exception:
        logger.exception("Could not create a conversation.")
        return None


def add_message(conversation_id: int | None, role: str, content: str,
                attachments: list[str] | None = None) -> None:
    """Record one visible turn. The first user message names the chat."""
    if conversation_id is None or role not in ("user", "assistant"):
        return
    content = content or ""
    names = [a for a in (attachments or []) if a]
    if not content.strip() and not names:
        return
    try:
        now = time.time()
        _db().execute(
            "INSERT INTO conversation_messages "
            "(conversation_id, role, content, attachments, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (conversation_id, role, content, json.dumps(names) if names else "", now),
        )
        if role == "user":
            title = _title_from(content) or (
                "Attached " + ", ".join(names) if names else "")
            _db().execute(
                "UPDATE conversations SET updated_at = ?, "
                "title = CASE WHEN title = '' THEN ? ELSE title END WHERE id = ?",
                (now, title, conversation_id),
            )
        else:
            _db().execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?",
                (now, conversation_id),
            )
        _db().commit()
    except Exception:
        logger.exception("Could not save a conversation message.")


def set_summary(conversation_id: int | None, summary: str) -> None:
    if conversation_id is None:
        return
    try:
        _db().execute(
            "UPDATE conversations SET summary = ? WHERE id = ?",
            (summary or "", conversation_id),
        )
        _db().commit()
    except Exception:
        logger.exception("Could not save a conversation summary.")


def get(conversation_id: int) -> dict[str, Any] | None:
    try:
        row = _db().execute(
            "SELECT id, title, summary, created_at, updated_at "
            "FROM conversations WHERE id = ?", (conversation_id,),
        ).fetchone()
        return dict(row) if row else None
    except Exception:
        logger.exception("Could not read a conversation.")
        return None


def messages(conversation_id: int) -> list[dict[str, Any]]:
    try:
        rows = _db().execute(
            "SELECT role, content, attachments, created_at "
            "FROM conversation_messages WHERE conversation_id = ? ORDER BY id",
            (conversation_id,),
        ).fetchall()
    except Exception:
        logger.exception("Could not read conversation messages.")
        return []
    out = []
    for r in rows:
        item = dict(r)
        try:
            item["attachments"] = json.loads(item["attachments"]) if item["attachments"] else []
        except Exception:
            item["attachments"] = []
        out.append(item)
    return out


def recent(limit: int = 100) -> list[dict[str, Any]]:
    """Conversations that have at least one message, most recent first."""
    try:
        rows = _db().execute(
            "SELECT c.id, c.title, c.updated_at, COUNT(m.id) AS message_count "
            "FROM conversations c JOIN conversation_messages m "
            "ON m.conversation_id = c.id "
            "GROUP BY c.id ORDER BY c.updated_at DESC, c.id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        logger.exception("Could not list conversations.")
        return []


def latest() -> dict[str, Any] | None:
    rows = recent(limit=1)
    return rows[0] if rows else None


def delete(conversation_id: int) -> None:
    try:
        _db().execute(
            "DELETE FROM conversation_messages WHERE conversation_id = ?",
            (conversation_id,),
        )
        _db().execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
        _db().commit()
    except Exception:
        logger.exception("Could not delete a conversation.")
