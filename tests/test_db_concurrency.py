"""SQLite under real concurrent access, from real threads.

Every local store (activity, memory, revert, situation, projects, capability
probe) shares one shape: a module-level connection opened once with
`check_same_thread=False`, reached from the UI thread, a worker thread, and a
cancelled turn's own cleanup. Nothing had ever exercised two of those callers
at the same instant — every existing test drove a store from one thread —
and a lock bug only shows up when two callers actually overlap.

Hammering six threads against activity_store and memory_store at once
produced, before the fix in brain/_local_db.py: `sqlite3.OperationalError:
database is locked`, one run that simply hung, and a row whose content came
back None mid-scan. All three came from the same root cause — a bare
sqlite3.Connection has no lock of its own, and neither the check-then-set
that lazily creates it nor the fetch that follows an execute is safe to run
from two threads at once.
"""
from __future__ import annotations

import os
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests import _isolate  # noqa: F401


def _run_concurrently(*targets_and_args, timeout=30) -> list[Exception]:
    """Run several callables in parallel threads; collect what they raised."""
    errors: list[Exception] = []
    lock = threading.Lock()

    def wrap(fn, args):
        try:
            fn(*args)
        except Exception as exc:  # noqa: BLE001 - collecting for the assertion
            with lock:
                errors.append(exc)

    threads = [threading.Thread(target=wrap, args=(fn, args))
               for fn, args in targets_and_args]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=timeout)

    hung = [t for t in threads if t.is_alive()]
    assert not hung, f"{len(hung)} thread(s) never finished — a lock is stuck"
    return errors


def test_concurrent_activity_writes_are_never_lost():
    """Ten threads writing and reading activity rows at once. Every row
    written must be findable afterwards with the outcome that was set —
    the exact case get(row_id) exists for."""
    from brain import activity_store

    lost: list[str] = []
    lock = threading.Lock()

    def hammer(n: int) -> None:
        for i in range(n):
            row = activity_store.begin(f"concurrent action {i}")
            if row is None:
                with lock:
                    lost.append(f"begin() returned None on attempt {i}")
                continue
            activity_store.complete(row, "done", succeeded=True)
            got = activity_store.get(row)
            if got is None or got["outcome"] != "done":
                with lock:
                    lost.append(f"row {row} unreadable or wrong right after writing it")

    errors = _run_concurrently(*[(hammer, (60,)) for _ in range(5)])
    assert not errors, f"threads raised: {errors}"
    assert not lost, f"{len(lost)} row(s) lost or corrupted: {lost[:5]}"


def test_concurrent_recall_does_not_crash_while_writes_happen():
    from brain import activity_store

    def writer(n: int) -> None:
        for i in range(n):
            activity_store.complete(activity_store.begin(f"w{i}"), "ok")

    def reader(n: int) -> None:
        for _ in range(n):
            activity_store.recent(limit=20)

    errors = _run_concurrently(
        (writer, (80,)), (writer, (80,)), (reader, (150,)), (reader, (150,)),
    )
    assert not errors, f"threads raised: {errors}"


def test_concurrent_memory_writes_and_forgets_never_corrupt_a_row():
    """The bug found by this exact scenario: a row's content came back None
    mid-scan while one thread wrote memories and another deleted them."""
    from brain import memory_store

    def writer(tag: str, n: int) -> None:
        for i in range(n):
            memory_store.remember(f"fact {tag} number {i}", "fact")

    def forgetter(n: int) -> None:
        for _ in range(n):
            memory_store.forget(query="fact")
            memory_store.recall(query="fact")

    errors = _run_concurrently(
        (writer, ("A", 60)), (writer, ("B", 60)), (forgetter, (30,)),
    )
    assert not errors, f"threads raised: {errors}"


def test_the_lazy_connection_is_created_exactly_once_under_contention():
    """The check-then-set that lazily opens the connection — `if _conn is
    None: _conn = _connect()` — has no lock around it in the store itself.
    Ten threads calling _db() for the first time at once used to be able to
    all see None and all open their own connection to the same file, which
    is where the CREATE TABLE statements collided."""
    import importlib
    import tempfile

    os.environ["MIKE_DATA_DIR"] = tempfile.mkdtemp(prefix="mike-conn-race-")
    from brain import situation_store
    importlib.reload(situation_store)

    seen: set[int] = set()
    lock = threading.Lock()

    def touch() -> None:
        conn = situation_store._db()
        with lock:
            seen.add(id(conn))

    errors = _run_concurrently(*[(touch, ()) for _ in range(15)])
    assert not errors, f"threads raised: {errors}"
    assert len(seen) == 1, f"{len(seen)} separate connections were created"


def test_locked_connection_serializes_execute_and_fetch():
    """The narrower unit-level guarantee under _test_db_concurrency's real
    conditions: a LockedConnection used from many threads never raises and
    never returns a row that does not match what was inserted."""
    import tempfile

    from brain._local_db import connect

    path = os.path.join(tempfile.mkdtemp(prefix="mike-locked-"), "t.db")
    conn = connect(path)
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, value TEXT NOT NULL)")
    conn.commit()

    def writer(tag: str, n: int) -> None:
        for i in range(n):
            conn.execute("INSERT INTO t (value) VALUES (?)", (f"{tag}-{i}",))
            conn.commit()

    def reader(n: int) -> None:
        for _ in range(n):
            rows = conn.execute("SELECT value FROM t").fetchall()
            for row in rows:
                assert row["value"] is not None, "a row came back with no value"

    errors = _run_concurrently(
        (writer, ("A", 100)), (writer, ("B", 100)), (reader, (100,)), (reader, (100,)),
    )
    assert not errors, f"threads raised: {errors}"
