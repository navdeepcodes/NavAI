"""Missions — what the user is trying to get done, kept until it is done.

A conversation remembers what was said. A mission remembers what someone is
*trying to accomplish*: the goal, the steps, the files the work lives in, what
is finished, what is next, and what is in the way. It survives switching
apps, closing Mike and restarting the computer, and it is what Mike picks up
from when he's opened again.

Progress is evidence, not assertion. A step about a part of a document
("Write the Results section") is linked to that section and ticks itself when
the document really contains it — and un-ticks if it's deleted. The model
cannot mark such a step done by saying so; it can only mark the steps no file
can show (read the brief, proofread, submit), and those are labelled as
"you said so" rather than verified.

One mission is active at a time. That is deliberate: this is "the thing I'm
getting done tonight", not a task manager.

Same local database and locking discipline as the other stores.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from brain import mission_checks as checks
from hostplatform import storage
from logs.logger import logger

_DB_DIR = storage.data_dir()
_DB_PATH = _DB_DIR / "memory.db"

MAX_STEPS = 10


class MissionError(Exception):
    """A mission request that can't be honoured, in words to pass on."""


def _connect() -> sqlite3.Connection:
    _DB_DIR.mkdir(parents=True, exist_ok=True)
    from brain._local_db import connect as _locked_connect
    conn = _locked_connect(str(_DB_PATH))
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS missions (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            goal            TEXT    NOT NULL,
            status          TEXT    NOT NULL DEFAULT 'active',
            deadline        TEXT    NOT NULL DEFAULT '',
            context         TEXT    NOT NULL DEFAULT '',
            blocker         TEXT    NOT NULL DEFAULT '',
            conversation_id INTEGER,
            snapshot        TEXT    NOT NULL DEFAULT '',
            seen_snapshot   TEXT    NOT NULL DEFAULT '',
            created_at      REAL    NOT NULL,
            updated_at      REAL    NOT NULL,
            finished_at     REAL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS mission_steps (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            mission_id  INTEGER NOT NULL,
            position    INTEGER NOT NULL,
            title       TEXT    NOT NULL,
            section     TEXT    NOT NULL DEFAULT '',
            target      INTEGER NOT NULL DEFAULT 0,
            status      TEXT    NOT NULL DEFAULT 'todo',
            evidence    TEXT    NOT NULL DEFAULT '',
            updated_at  REAL    NOT NULL
        )
        """
    )
    cols = [r[1] for r in conn.execute("PRAGMA table_info(mission_steps)")]
    if "guidance" not in cols:
        conn.execute("ALTER TABLE mission_steps ADD COLUMN guidance TEXT NOT NULL DEFAULT ''")
    if "seen_at" not in [r[1] for r in conn.execute("PRAGMA table_info(missions)")]:
        conn.execute("ALTER TABLE missions ADD COLUMN seen_at REAL")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS mission_files (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            mission_id  INTEGER NOT NULL,
            path        TEXT    NOT NULL,
            role        TEXT    NOT NULL DEFAULT 'work',
            added_at    REAL    NOT NULL
        )
        """
    )
    conn.commit()
    return conn


_conn: sqlite3.Connection | None = None
_conn_lock = threading.Lock()
# Serialises read-modify-write sequences (evaluate, set_step) between the UI's
# file watcher and a tool call on the worker thread.
_write_lock = threading.RLock()


def _db() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        with _conn_lock:
            if _conn is None:
                _conn = _connect()
    return _conn


# ── reading ───────────────────────────────────────────────

def get(mission_id: int) -> dict | None:
    row = _db().execute(
        "SELECT id, goal, status, deadline, context, blocker, conversation_id, "
        "created_at, updated_at, finished_at FROM missions WHERE id = ?", (mission_id,),
    ).fetchone()
    if row is None:
        return None
    keys = ("id", "goal", "status", "deadline", "context", "blocker",
            "conversation_id", "created_at", "updated_at", "finished_at")
    mission = dict(zip(keys, row))
    mission["steps"] = [
        dict(zip(("id", "position", "title", "section", "target", "status", "evidence", "guidance"), r))
        for r in _db().execute(
            "SELECT id, position, title, section, target, status, evidence, guidance "
            "FROM mission_steps WHERE mission_id = ? ORDER BY position", (mission_id,))
    ]
    mission["files"] = [
        {"path": r[0], "role": r[1]}
        for r in _db().execute(
            "SELECT path, role FROM mission_files WHERE mission_id = ? ORDER BY id", (mission_id,))
    ]
    return mission


def active() -> dict | None:
    try:
        row = _db().execute(
            "SELECT id FROM missions WHERE status = 'active' ORDER BY updated_at DESC LIMIT 1"
        ).fetchone()
    except Exception:
        logger.exception("Could not read the active mission.")
        return None
    return get(int(row[0])) if row else None


def recent(limit: int = 10) -> list[dict]:
    rows = _db().execute(
        "SELECT id FROM missions ORDER BY updated_at DESC LIMIT ?", (limit,)).fetchall()
    return [m for m in (get(int(r[0])) for r in rows) if m]


def progress(mission: dict) -> tuple[int, int]:
    steps = mission.get("steps", [])
    return sum(1 for s in steps if s["status"] == "done"), len(steps)


def next_step(mission: dict) -> dict | None:
    return next((s for s in mission.get("steps", []) if s["status"] != "done"), None)


# ── writing ───────────────────────────────────────────────

def _touch(mission_id: int) -> None:
    _db().execute("UPDATE missions SET updated_at = ? WHERE id = ?", (time.time(), mission_id))


def start(goal: str, steps: list[str], files: list[str] | tuple = (),
          deadline: str = "", context: str = "", brief: list[str] | tuple = ()) -> dict:
    """Start a mission with the plan the model made.

    The steps are kept exactly as given, in the given order. What the harness
    adds is evidence: a step about a section of the user's document is tied
    to that section, and is then checked from the file rather than taken on
    anyone's word.
    """
    goal = " ".join((goal or "").split())
    titles = [" ".join(str(s).split()) for s in (steps or []) if str(s).strip()][:MAX_STEPS]
    if not goal:
        raise MissionError("A mission needs a goal.")
    if not titles:
        raise MissionError("A mission needs its steps: the parts of the work, in order.")
    current = active()
    if current is not None:
        raise MissionError(
            f"Already working on a mission: “{current['goal']}”. Finish or drop "
            "it first, or add to it instead of starting another.")
    # Files first: a path that doesn't exist should stop the mission before
    # anything is written, not leave a half-made one behind.
    resolved = [(_resolve(f), "brief") for f in brief or []]
    resolved += [(p, _role(p, "work")) for p in (_resolve(f) for f in files or [])
                 if all(p != q for q, _ in resolved)]
    with _write_lock:
        now = time.time()
        cur = _db().execute(
            "INSERT INTO missions (goal, deadline, context, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (goal, (deadline or "").strip(), (context or "").strip(), now, now))
        mission_id = int(cur.lastrowid)
        for i, title in enumerate(titles):
            _db().execute(
                "INSERT INTO mission_steps (mission_id, position, title, updated_at) "
                "VALUES (?, ?, ?, ?)", (mission_id, i, title, now))
        for path, role in resolved:
            _db().execute(
                "INSERT INTO mission_files (mission_id, path, role, added_at) VALUES (?, ?, ?, ?)",
                (mission_id, str(path), role, now))
        _db().commit()
        _link_steps(mission_id)
        evaluate(mission_id)
        mark_seen(mission_id)
    mission = get(mission_id)
    logger.info("Mission started: %s (%d steps)", goal, len(mission["steps"]))
    return mission


def _resolve(path: str) -> Path:
    raw = str(path or "").strip().strip('"').strip("'")
    if not raw:
        raise MissionError("No file path was given.")
    p = Path(raw).expanduser()
    if not p.is_absolute():
        try:
            from tools.filesystem.path_utils import resolve_path
            p = Path(resolve_path(raw))
        except Exception:
            p = p.resolve()
    if not p.exists():
        raise MissionError(f"{raw} doesn't exist. Check the path, or ask the user where the file is.")
    return p


def _role(path: Path, wanted: str) -> str:
    """The role a file plays. A format nobody writes in (a PDF, slides) can
    only be read, so it is the brief whatever it was passed as."""
    return wanted if wanted == "brief" or path.suffix.lower() in checks.WRITABLE else "brief"


def add_file(mission_id: int, path: str, role: str | None = None) -> dict:
    p = _resolve(path)
    with _write_lock:
        exists = _db().execute(
            "SELECT 1 FROM mission_files WHERE mission_id = ? AND lower(path) = lower(?)",
            (mission_id, str(p))).fetchone()
        if not exists:
            _db().execute(
                "INSERT INTO mission_files (mission_id, path, role, added_at) VALUES (?, ?, ?, ?)",
                (mission_id, str(p), _role(p, role if role in ("work", "brief") else "work"), time.time()))
            _touch(mission_id)
            _db().commit()
        _link_steps(mission_id)
        evaluate(mission_id)
    return get(mission_id)


def _brief_text(mission: dict) -> str:
    from tools.filesystem.document_reader import read_document
    texts = []
    for f in mission["files"]:
        if f["role"] == "brief":
            try:
                texts.append(read_document(f["path"]))
            except Exception:
                logger.debug("Could not read brief %s", f["path"], exc_info=True)
    return "\n".join(texts)


def _link_steps(mission_id: int, shapes: list | None = None, from_brief: bool = True) -> None:
    """Tie each step still unlinked to the document section it is about, and
    take its target length from the brief when the brief states one.

    At the start the brief's own headings count, so "Write the Discussion"
    shows "no Discussion section yet" before there is one; later, a heading
    the user adds links the step that names it.
    """
    mission = get(mission_id)
    if mission is None:
        return
    unlinked = [s for s in mission["steps"] if not s["section"]]
    if not unlinked:
        return
    if shapes is None:
        shapes = [checks.outline(f["path"]) for f in mission["files"] if f["role"] == "work"]
    headings: list[str] = []
    for shape in shapes:
        if shape and "order" in shape:
            headings += [h for h in shape["order"] if h not in headings]
    brief = _brief_text(mission) if from_brief else None
    if brief:
        headings += [h for h in checks.brief_headings(brief) if h not in headings]
    links = [(s, checks.link_step(s["title"], headings)) for s in unlinked]
    links = [(s, section) for s, section in links if section]
    if not links:
        return
    if brief is None:
        brief = _brief_text(mission)
    for step, section in links:
        # the length the model put in its own step ("Write the Discussion
        # (150-200 words)"), else the brief's, else a plain minimum
        target = (checks.target_words(step["title"], section) or checks.target_words(brief, section)
                  or checks.DEFAULT_MIN_WORDS)
        _db().execute("UPDATE mission_steps SET section = ?, target = ?, guidance = ? WHERE id = ?",
                      (section, target, checks.guidance(brief, section), step["id"]))
    _db().commit()


def evaluate(mission_id: int) -> dict:
    """Read the work files and bring every checked step in line with them.

    Returns {"mission": ..., "changes": [...], "newly_done": [...]} where
    changes are what moved since the last evaluation.
    """
    with _write_lock:
        mission = get(mission_id)
        if mission is None:
            return {"mission": None, "changes": [], "newly_done": []}
        work = [f["path"] for f in mission["files"] if f["role"] == "work"]
        old = _load_snapshot(mission_id, "snapshot")
        snap = {path: checks.outline(path) for path in work}
        _link_steps(mission_id, list(snap.values()), from_brief=False)
        mission = get(mission_id)

        newly_done = []
        now = time.time()
        for step in mission["steps"]:
            if not step["section"] or not work:
                continue
            status, evidence = _judge(step, snap)
            if status is None:
                continue                    # couldn't read: keep what we knew
            if status != step["status"] or evidence != step["evidence"]:
                if status == "done" and step["status"] != "done":
                    newly_done.append(step["title"])
                _db().execute(
                    "UPDATE mission_steps SET status = ?, evidence = ?, updated_at = ? WHERE id = ?",
                    (status, evidence, now, step["id"]))

        changes = []
        for path in work:
            changes += checks.describe_changes((old or {}).get(path), snap.get(path), Path(path).name)
        _db().execute("UPDATE missions SET snapshot = ? WHERE id = ?",
                      (json.dumps(snap), mission_id))
        if changes or newly_done:
            _touch(mission_id)
        _db().commit()
        return {"mission": get(mission_id), "changes": changes, "newly_done": newly_done}


def _judge(step: dict, snap: dict) -> tuple[str | None, str]:
    readable = False
    for path, shape in snap.items():
        name = Path(path).name
        if shape is None:
            continue
        if "error" in shape:
            continue
        readable = True
        heading = checks.find_section(shape["sections"], step["section"])
        if heading is None:
            continue
        words, target = shape["sections"][heading], step["target"] or checks.DEFAULT_MIN_WORDS
        evidence = f"{words}/{target} words in {heading} ({name})"
        return ("done" if words >= checks.needed(target) else "todo"), evidence
    if not readable:
        missing = [Path(p).name for p, s in snap.items() if s is None]
        if missing:
            return "todo", f"{', '.join(missing)} not found"
        return None, ""
    return "todo", f"no “{step['section']}” section yet"


def _load_snapshot(mission_id: int, column: str) -> dict:
    row = _db().execute(f"SELECT {column} FROM missions WHERE id = ?", (mission_id,)).fetchone()
    try:
        return json.loads(row[0]) if row and row[0] else {}
    except ValueError:
        return {}


def changes_since_seen(mission_id: int) -> list[str]:
    """What moved in the work since the user last saw this mission."""
    seen = _load_snapshot(mission_id, "seen_snapshot")
    now = _load_snapshot(mission_id, "snapshot")
    out = []
    for path, shape in now.items():
        out += checks.describe_changes(seen.get(path), shape, Path(path).name)
    return out


def mark_seen(mission_id: int) -> None:
    with _write_lock:
        _db().execute("UPDATE missions SET seen_snapshot = snapshot, seen_at = ? WHERE id = ?",
                      (time.time(), mission_id))
        _db().commit()


def seen_ago(mission_id: int) -> float | None:
    """Seconds since the user last had this mission in front of them."""
    row = _db().execute("SELECT seen_at FROM missions WHERE id = ?", (mission_id,)).fetchone()
    return (time.time() - float(row[0])) if row and row[0] else None


def _find_step(mission: dict, ref) -> dict | None:
    steps = mission["steps"]
    text = str(ref if ref is not None else "").strip()
    if text.isdigit() and 1 <= int(text) <= len(steps):
        return steps[int(text) - 1]
    wanted = text.casefold()
    if not wanted:
        return None
    for s in steps:
        if s["title"].casefold() == wanted:
            return s
    for s in steps:
        if wanted in s["title"].casefold() or (s["section"] and s["section"].casefold() in wanted):
            return s
    return None


def set_step(mission_id: int, ref, status: str, note: str = "") -> str:
    """Mark a step. Returns what happened, in words to pass on."""
    status = (status or "").strip().lower()
    if status not in ("done", "todo", "blocked"):
        raise MissionError("A step's status is done, todo or blocked.")
    with _write_lock:
        mission = get(mission_id)
        step = _find_step(mission, ref) if mission else None
        if step is None:
            raise MissionError(f"No step matching {ref!r}. Steps: "
                               + "; ".join(f"{i + 1}. {s['title']}" for i, s in enumerate(mission["steps"])))
        if step["section"] and status == "done":
            # Checked from the document: only the document can tick it.
            result = evaluate(mission_id)
            now = next(s for s in result["mission"]["steps"] if s["id"] == step["id"])
            if now["status"] == "done":
                return f"“{step['title']}” is done — verified: {now['evidence']}."
            return (f"Not marked done: {now['evidence'] or 'the section is not written yet'}. "
                    "This step is checked from the document, so it ticks itself once it's written.")
        # A step no file can show is done on the user's word, and says so.
        note = " ".join((note or "").split())
        evidence = ("you said so" + (f": {_short(note, 40)}" if note else "")) if status == "done" else note
        _db().execute(
            "UPDATE mission_steps SET status = ?, evidence = ?, updated_at = ? WHERE id = ?",
            (status, evidence, time.time(), step["id"]))
        if status == "blocked":
            _db().execute("UPDATE missions SET blocker = ? WHERE id = ?",
                          (note.strip() or step["title"], mission_id))
        elif mission["blocker"] and status == "done":
            _db().execute("UPDATE missions SET blocker = '' WHERE id = ?", (mission_id,))
        _touch(mission_id)
        _db().commit()
    return f"“{step['title']}” marked {status}" + (f" ({evidence})" if evidence else "") + "."


def set_blocker(mission_id: int, text: str) -> None:
    _db().execute("UPDATE missions SET blocker = ? WHERE id = ?", ((text or "").strip(), mission_id))
    _touch(mission_id)
    _db().commit()


def finish(mission_id: int, status: str = "done") -> str:
    status = "dropped" if str(status).lower() in ("dropped", "drop", "abandoned", "cancel", "cancelled") else "done"
    with _write_lock:
        if status == "done":
            result = evaluate(mission_id)
            unmet = [s for s in result["mission"]["steps"] if s["section"] and s["status"] != "done"]
            if unmet:
                raise MissionError(
                    "Not finished yet — the document doesn't show it: "
                    + "; ".join(f"{s['title']} ({s['evidence']})" for s in unmet)
                    + ". If the user wants to stop anyway, drop the mission instead.")
            _db().execute(
                "UPDATE mission_steps SET status = 'done', evidence = 'finished' "
                "WHERE mission_id = ? AND status != 'done'", (mission_id,))
        now = time.time()
        _db().execute("UPDATE missions SET status = ?, finished_at = ?, updated_at = ? WHERE id = ?",
                      (status, now, now, mission_id))
        _db().commit()
    mission = get(mission_id)
    logger.info("Mission %s: %s", status, mission["goal"] if mission else mission_id)
    return f"Mission {status}: “{mission['goal']}”." if mission else f"Mission {status}."


def complete_if_done(mission_id: int) -> bool:
    """Finish the mission once every step is done — sections verified from
    the file, the rest as the user said. Returns whether it just finished."""
    mission = get(mission_id)
    if not mission or mission["status"] != "active" or not mission["steps"]:
        return False
    if any(s["status"] != "done" for s in mission["steps"]):
        return False
    try:
        finish(mission_id, "done")
    except MissionError:
        return False
    return True


def bind_conversation(mission_id: int, conversation_id: int | None) -> None:
    if conversation_id is None:
        return
    _db().execute("UPDATE missions SET conversation_id = ? WHERE id = ? AND conversation_id IS NULL",
                  (conversation_id, mission_id))
    _db().commit()


# ── telling people (and the model) where things stand ───

def _short(text: str, n: int = 34) -> str:
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def context_line(mission: dict) -> str:
    """The mission as the model sees it each turn: compact, and true."""
    done, total = progress(mission)
    nxt = next_step(mission)
    marks = " · ".join(
        ("✓" if s["status"] == "done" else "⛔" if s["status"] == "blocked" else "□")
        + _short(s["title"]) + (f" ({s['evidence']})" if s["section"] and s["status"] != "done" and s["evidence"] else "")
        for s in mission["steps"])
    files = ", ".join(f"{f['path']}" + (" [brief]" if f["role"] == "brief" else "") for f in mission["files"])
    parts = [f"Active mission: {mission['goal']}"
             + (f" (due {mission['deadline']})" if mission["deadline"] else "")
             + f". {done}/{total} steps done.",
             f"Steps: {marks}."]
    if nxt:
        parts.append(f"Next: {nxt['title']}.")
        # the next section's own brief, so coaching it needs no extra read
        upcoming = [s for s in mission["steps"] if s["status"] != "done" and s.get("guidance")][:2]
        for s in upcoming:
            parts.append(f"Brief for {s['section']}: {s['guidance']}")
        # and what they last wrote, so the next part can build on it
        written = _latest_written(mission)
        if written:
            parts.append(f"What they wrote in {written[0]}: “{written[1]}”")
    if mission["blocker"]:
        parts.append(f"Blocked by: {mission['blocker']}.")
    if files:
        parts.append(f"Files: {files}.")
    parts.append("Steps about a section of their document tick by themselves when the file "
                 "shows it. The others (reading the brief, submitting) tick only when you mark "
                 "them with the mission tool, once the user says they've done them.")
    return "\n".join(parts)


def _latest_written(mission: dict) -> tuple[str, str] | None:
    """(section, excerpt) of the last finished section step, from the file."""
    done = [s for s in mission["steps"] if s["section"] and s["status"] == "done"]
    if not done:
        return None
    snap = _load_snapshot(mission["id"], "snapshot")
    for step in reversed(done):
        for shape in snap.values():
            if not shape or "error" in shape:
                continue
            heading = checks.find_section(shape.get("sections", {}), step["section"])
            text = (shape.get("excerpts") or {}).get(heading or "", "")
            if text:
                return heading, text
    return None


def status_text(mission: dict) -> str:
    """One line for a person: 'Lab report · 2 of 5 · next: Results (40/150 words)'."""
    done, total = progress(mission)
    nxt = next_step(mission)
    line = f"{_short(mission['goal'], 48)} · {done} of {total}"
    if nxt is None:
        return line + " · all done"
    detail = f" ({nxt['evidence'].split(' in ')[0]})" if nxt["section"] and "/" in nxt["evidence"] else ""
    return line + f" · next: {_short(nxt['title'], 40)}{detail}"
