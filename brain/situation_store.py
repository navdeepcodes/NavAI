from __future__ import annotations

import sqlite3
import time
from pathlib import Path

_DB_DIR = Path.home() / "Library" / "Application Support" / "Mike"
_DB_PATH = _DB_DIR / "memory.db"


def _connect() -> sqlite3.Connection:
    _DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH), timeout=5, check_same_thread=False)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS situation (
            id         INTEGER PRIMARY KEY CHECK (id = 1),
            summary    TEXT    NOT NULL,
            updated_at REAL    NOT NULL
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


def load() -> str:

    row = _db().execute(
        "SELECT summary FROM situation WHERE id = 1"
    ).fetchone()

    return row[0] if row else ""


def save(summary: str) -> None:

    _db().execute(
        """
        INSERT INTO situation (id, summary, updated_at)
        VALUES (1, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            summary = excluded.summary,
            updated_at = excluded.updated_at
        """,
        (summary, time.time()),
    )

    _db().commit()
