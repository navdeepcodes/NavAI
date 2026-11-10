"""Carry out an approved plan, and undo it.

Every run writes a journal to disk *before* the first file moves, listing
every move it is about to make. Undo works from that journal, so it still
works after a crash, a force-quit, or a restart halfway through a run.

Undo trusts the disk, not the journal's bookkeeping: for each move it looks
at where the file actually is now. A file the user has since moved, renamed
or replaced is reported and left alone -- undo never overwrites anything.

Nothing here deletes a user's file. The only removals are folders this run
created itself, and only once they are empty again (a Finder ``.DS_Store``
left behind by browsing the folder doesn't count as content).
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from organizer.plan import Plan

# Rewriting the journal after every single move would be quadratic on a
# folder of thousands of files. Undo reads the disk anyway, so the "done"
# flags are bookkeeping, and checkpointing every few dozen moves is enough.
_CHECKPOINT_EVERY = 25
_FINDER_LITTER = frozenset({".DS_Store", ".localized"})


def _runs_dir() -> Path:
    from hostplatform import storage

    path = storage.data_dir() / "organizer" / "runs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _save(journal: dict) -> None:
    path = _runs_dir() / f"{journal['run_id']}.json"
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(journal, indent=1), encoding="utf-8")
    os.replace(tmp, path)  # never a half-written journal


def _load(run_id: str) -> dict:
    return json.loads((_runs_dir() / f"{run_id}.json").read_text(encoding="utf-8"))


@dataclass
class RunResult:
    run_id: str
    moved: int = 0
    failed: list[tuple[str, str]] = field(default_factory=list)  # (path, why)


@dataclass
class UndoResult:
    run_id: str
    restored: int = 0
    already_back: int = 0
    left_alone: list[tuple[str, str]] = field(default_factory=list)  # (path, why)


def apply_plan(plan: Plan) -> RunResult:
    # Microseconds, not a random suffix: run ids must sort in the order the
    # runs happened, because "undo" with no id means "the latest run". Two
    # runs inside one second used to sort by a random token and undo the
    # wrong one.
    now = datetime.now()
    run_id = f"{now:%Y%m%d-%H%M%S-%f}"
    while (_runs_dir() / f"{run_id}.json").exists():
        run_id += "x"
    journal = {
        "run_id": run_id,
        "root": str(plan.root),
        "created_at": now.isoformat(timespec="seconds"),
        "state": "applying",
        "created_dirs": [],
        "moves": [{"src": str(m.src), "dst": str(m.dst), "done": False, "error": None}
                  for m in plan.moves],
        "undone_at": None,
    }
    _save(journal)  # written before anything moves

    result = RunResult(run_id=run_id)
    for index, record in enumerate(journal["moves"], start=1):
        src, dst = Path(record["src"]), Path(record["dst"])
        error = _move_one(src, dst, journal["created_dirs"])
        if error:
            record["error"] = error
            result.failed.append((record["src"], error))
        else:
            record["done"] = True
            result.moved += 1
        if index % _CHECKPOINT_EVERY == 0:
            _save(journal)

    journal["state"] = "partial" if result.failed else "applied"
    _save(journal)
    return result


def _move_one(src: Path, dst: Path, created_dirs: list[str]) -> str | None:
    """Move one file, refusing to overwrite. Returns why it failed, or None."""
    if not src.exists():
        return "it was moved or deleted since the plan was made"
    if dst.exists() or dst.is_symlink():
        # The plan checked this, but the folder may have changed since.
        # Overwriting would destroy a file, so this move is skipped instead.
        return f"something named {dst.name} appeared there since the plan was made"
    try:
        _make_dirs(dst.parent, created_dirs)
        os.rename(src, dst)
    except OSError as exc:
        return exc.strerror or str(exc)
    return None


def _make_dirs(folder: Path, created_dirs: list[str]) -> None:
    missing: list[Path] = []
    current = folder
    while not current.exists():
        missing.append(current)
        current = current.parent
    for path in reversed(missing):
        path.mkdir()
        created_dirs.append(str(path))


def undo_run(run_id: str | None = None) -> UndoResult:
    """Put every file from a run back where it was. Defaults to the most
    recent run that hasn't been undone."""
    if run_id is None:
        candidates = [r for r in list_runs() if r["state"] != "undone"]
        if not candidates:
            raise LookupError("There's no organize run to undo.")
        run_id = candidates[0]["run_id"]

    journal = _load(run_id)
    if journal["state"] == "undone":
        raise LookupError("That run has already been undone.")

    result = UndoResult(run_id=run_id)
    for record in reversed(journal["moves"]):
        if record.get("error") and not record["done"]:
            continue  # this move never happened
        src, dst = Path(record["src"]), Path(record["dst"])
        at_dst = dst.exists() or dst.is_symlink()
        at_src = src.exists() or src.is_symlink()
        if at_dst and not at_src:
            try:
                src.parent.mkdir(parents=True, exist_ok=True)
                os.rename(dst, src)
                result.restored += 1
                record["done"] = False
            except OSError as exc:
                result.left_alone.append((str(dst), exc.strerror or str(exc)))
        elif at_src and not at_dst:
            result.already_back += 1  # put back by hand, or the run stopped first
            record["done"] = False
        elif at_src and at_dst:
            result.left_alone.append((str(dst), f"{src.name} already exists at its old place"))
        else:
            result.left_alone.append((str(src), "it's no longer where this run put it"))

    for folder in reversed(journal["created_dirs"]):
        _remove_if_empty(Path(folder))

    journal["state"] = "partly-undone" if result.left_alone else "undone"
    journal["undone_at"] = datetime.now().isoformat(timespec="seconds")
    _save(journal)
    return result


def _remove_if_empty(folder: Path) -> None:
    try:
        entries = list(folder.iterdir())
    except OSError:
        return
    if any(e.name not in _FINDER_LITTER for e in entries):
        return
    try:
        for litter in entries:
            litter.unlink()
        folder.rmdir()
    except OSError:
        pass


def list_runs() -> list[dict]:
    """Newest first: run_id, root, created_at, state, and the number of moves."""
    runs = []
    for path in _runs_dir().glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        runs.append({
            "run_id": data["run_id"], "root": data["root"],
            "created_at": data["created_at"], "state": data["state"],
            "moves": len(data["moves"]),
        })
    runs.sort(key=lambda r: r["run_id"], reverse=True)
    return runs
