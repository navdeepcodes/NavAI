"""A durable record of actions Mike actually performed.

Written only when a tool genuinely ran, and only from its real result — this
is a log of what happened, never of what was intended. Lives in the same local
database as everything else.
"""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any

_DB_DIR = Path.home() / "Library" / "Application Support" / "Mike"
_DB_PATH = _DB_DIR / "memory.db"

MAX_ROWS = 500


def _connect() -> sqlite3.Connection:
    _DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH), timeout=5, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS activity (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            action     TEXT    NOT NULL,
            outcome    TEXT    NOT NULL DEFAULT '',
            succeeded  INTEGER NOT NULL DEFAULT 1,
            started_at REAL    NOT NULL
        )
        """
    )
    conn.commit()
    return conn


_conn: sqlite3.Connection | None = None


def _db() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = _connect()
    return _conn


def begin(action: str) -> int | None:
    """Record that an action started. Returns its row id."""

    if not action or not action.strip():
        return None
    try:
        cur = _db().execute(
            "INSERT INTO activity (action, started_at) VALUES (?, ?)",
            (action.strip(), time.time()),
        )
        _db().commit()
        return cur.lastrowid
    except Exception:
        return None


def complete(row_id: int | None, outcome: str, succeeded: bool = True) -> None:
    """Close out an action with the result the tool actually returned."""

    if row_id is None:
        return
    try:
        _db().execute(
            "UPDATE activity SET outcome = ?, succeeded = ? WHERE id = ?",
            ((outcome or "").strip()[:400], 1 if succeeded else 0, row_id),
        )
        _db().commit()
        _trim()
    except Exception:
        pass


def recent(limit: int = 60) -> list[dict[str, Any]]:
    try:
        rows = _db().execute(
            "SELECT id, action, outcome, succeeded, started_at "
            "FROM activity ORDER BY started_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []


def clear() -> None:
    try:
        _db().execute("DELETE FROM activity")
        _db().commit()
    except Exception:
        pass


def _trim() -> None:
    try:
        _db().execute(
            "DELETE FROM activity WHERE id NOT IN "
            "(SELECT id FROM activity ORDER BY started_at DESC LIMIT ?)",
            (MAX_ROWS,),
        )
        _db().commit()
    except Exception:
        pass
