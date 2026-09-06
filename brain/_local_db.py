"""One connection, used safely from many threads.

Every local store here shares the same shape: a module-level SQLite
connection, opened once with `check_same_thread=False` so the UI thread, a
worker thread and a background task can all reach it. That flag disables
Python's *check* that a connection is only touched by the thread that opened
it — it does not make concurrent use of one connection safe. A `Connection`
object has no lock of its own, and two threads calling `execute()` /
`commit()` on it at the same time race on its internal state.

Found this way: hammering activity_store and memory_store from six threads
at once produced `sqlite3.OperationalError: database is locked`, and in one
run six threads sharing an unwrapped connection simply hung. Nothing in
those modules had ever been exercised under real concurrency before — every
existing test drove them from one thread, and a lock bug only shows up when
two callers actually overlap.

This wraps a connection so every statement and commit is serialized through
one lock, and adds a busy_timeout as defense in depth against the rarer case
of a second *process* (not thread) touching the same file. It is a few lines
because the underlying fix is a few lines; the alternative was repeating the
same lock at every one of the forty-five call sites this replaces.
"""
from __future__ import annotations

import sqlite3
import threading
from typing import Any


class _LockedCursor:
    """A cursor whose fetches share the connection's lock.

    Every call site here does `_db().execute(sql, params).fetchall()` —
    execute and fetch chained together. Locking only execute() left that
    chain half-protected: thread A's execute() would return its cursor and
    release the lock, and before A called fetchall() on it, thread B's
    execute() on the *same connection* could run. A single sqlite3
    connection is not documented as safe for that even across independent
    cursor objects, and it produced exactly this: rows whose content came
    back None mid-scan.
    """

    __slots__ = ("_cursor", "_lock")

    def __init__(self, cursor: sqlite3.Cursor, lock: threading.RLock) -> None:
        self._cursor = cursor
        self._lock = lock

    def fetchall(self) -> list:
        with self._lock:
            return self._cursor.fetchall()

    def fetchone(self):
        with self._lock:
            return self._cursor.fetchone()

    def fetchmany(self, *args, **kwargs) -> list:
        with self._lock:
            return self._cursor.fetchmany(*args, **kwargs)

    def __iter__(self):
        # `for row in conn.execute(...)` is used directly at a couple of call
        # sites; the whole result is materialized under the lock rather than
        # yielded lazily, so the cursor is never touched again once iteration
        # starts without the lock held.
        with self._lock:
            rows = self._cursor.fetchall()
        return iter(rows)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._cursor, name)


class LockedConnection:
    """A sqlite3.Connection where execute/executemany/commit/close, and the
    fetch that follows an execute, cannot interleave across threads."""

    __slots__ = ("_conn", "_lock")

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._lock = threading.RLock()

    def execute(self, *args: Any, **kwargs: Any) -> "_LockedCursor":
        with self._lock:
            return _LockedCursor(self._conn.execute(*args, **kwargs), self._lock)

    def executemany(self, *args: Any, **kwargs: Any) -> "_LockedCursor":
        with self._lock:
            return _LockedCursor(self._conn.executemany(*args, **kwargs), self._lock)

    def commit(self) -> None:
        with self._lock:
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def __getattr__(self, name: str) -> Any:
        # Row factory, isolation level and anything else read-only pass
        # straight through; only mutation needs the lock.
        return getattr(self._conn, name)


def connect(path: str, *, timeout: float = 5.0) -> LockedConnection:
    conn = sqlite3.connect(path, timeout=timeout, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    # A second Mike process (or a stray script) touching the same file is a
    # real possibility this timeout is for; the in-process lock above is what
    # the deadlock and the OperationalError actually needed.
    conn.execute("PRAGMA busy_timeout = 5000")
    return LockedConnection(conn)
