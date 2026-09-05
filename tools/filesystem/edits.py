"""Targeted file edits — the difference between changing three lines and
rewriting a file from memory.

Before this, the only way to modify a file was write_file: rewrite the whole
thing. That is unreliable for any model (everything not re-emitted is
silently lost) and wasteful for a large one. Exact-string replacement makes
a change addressable and, more importantly, verifiable: the edit either
matches or it doesn't, and the result says which.

Every edit returns a real unified diff of what actually changed on disk, so
the model observes the consequence of its own action rather than assuming it.
"""
from __future__ import annotations

import difflib
import os
from pathlib import Path

from tools.filesystem.path_utils import resolve_path


def _ensure_visible_change(file: Path, previous_mtime: float | None) -> None:
    """
    Guarantees the edit is visible to anything that caches by (mtime, size).

    CPython invalidates a .pyc using the source's integer-second mtime and its
    size. A same-length edit applied within the same second — `a - b` becoming
    `a + b` is exactly that — leaves both unchanged, so the next test run
    silently imports stale bytecode and reports the old behaviour. Verified:
    that produced a false "still failing" result immediately after a
    genuinely correct fix, which is the most misleading outcome verification
    can have. Nudging the mtime forward when it would otherwise collide costs
    nothing and removes the trap.
    """
    if previous_mtime is None:
        return
    try:
        current = file.stat().st_mtime
        if int(current) == int(previous_mtime):
            bumped = int(previous_mtime) + 1
            os.utime(file, (bumped, bumped))
    except OSError:
        pass

# A match must be unambiguous. Silently editing the first of several
# identical snippets is how an edit "succeeds" and corrupts a file.
AMBIGUOUS = "ambiguous"
NOT_FOUND = "not_found"


def _diff(before: str, after: str, path: str) -> str:
    lines = difflib.unified_diff(
        before.splitlines(keepends=True),
        after.splitlines(keepends=True),
        fromfile=f"a/{path}",
        tofile=f"b/{path}",
        n=3,
    )
    return "".join(lines)


def read_lines(path: str, offset: int = 1, limit: int = 400) -> dict:
    """
    Read a file with line numbers, optionally a slice of it.

    Line numbers are what make a subsequent edit targetable and let the model
    talk about a location precisely. offset is 1-based, matching how every
    editor, stack trace, and compiler error refers to lines.
    """
    file = resolve_path(path)

    if not file.exists():
        return {"status": "error", "error": f"No such file: {file}"}
    if file.is_dir():
        return {"status": "error", "error": f"{file} is a directory, not a file."}

    try:
        text = file.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return {"status": "error", "error": f"Could not read {file}: {exc}"}

    lines = text.splitlines()
    total = len(lines)

    if offset < 1:
        offset = 1
    start = offset - 1
    end = min(start + limit, total)
    window = lines[start:end]

    width = len(str(end)) if end else 1
    numbered = "\n".join(
        f"{str(start + i + 1).rjust(width)}\t{line}"
        for i, line in enumerate(window)
    )

    return {
        "status": "success",
        "path": str(file),
        "total_lines": total,
        "shown": f"{start + 1}-{end}" if window else "none",
        "truncated": end < total,
        "content": numbered,
    }


def edit_file(
    path: str,
    old_text: str,
    new_text: str,
    expect_count: int | None = None,
) -> dict:
    """
    Replace an exact snippet. Fails loudly rather than guessing.

    Not found or found more than once are both refusals, not silent partial
    successes — an edit the model believes happened but didn't is far worse
    than one that reports why it couldn't. When a snippet is ambiguous the
    result says how many times it matched, so the model can extend the
    snippet with surrounding context and retry, which is a decision it is
    well suited to make and the runtime is not.

    expect_count opts into replacing every occurrence deliberately.
    """
    file = resolve_path(path)

    if not file.exists():
        return {"status": "error", "error": f"No such file: {file}", "reason": NOT_FOUND}
    if file.is_dir():
        return {"status": "error", "error": f"{file} is a directory, not a file."}

    if not old_text:
        return {
            "status": "error",
            "error": "old_text must not be empty. To create or overwrite a whole file, use write_file.",
        }

    try:
        before = file.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return {"status": "error", "error": f"Could not read {file}: {exc}"}

    occurrences = before.count(old_text)

    if occurrences == 0:
        return {
            "status": "error",
            "reason": NOT_FOUND,
            "error": (
                f"That exact text does not appear in {file.name}. Nothing was "
                "changed. Read the file and match the text exactly, including "
                "indentation."
            ),
        }

    if occurrences > 1 and expect_count is None:
        return {
            "status": "error",
            "reason": AMBIGUOUS,
            "occurrences": occurrences,
            "error": (
                f"That text appears {occurrences} times in {file.name}, so it is "
                "ambiguous which one to change. Nothing was changed. Include "
                "more surrounding context to make it unique, or pass "
                f"expect_count={occurrences} to replace all of them."
            ),
        }

    if expect_count is not None and expect_count != occurrences:
        return {
            "status": "error",
            "reason": AMBIGUOUS,
            "occurrences": occurrences,
            "error": (
                f"Expected {expect_count} occurrences but found {occurrences} "
                f"in {file.name}. Nothing was changed."
            ),
        }

    # Snapshot before touching disk, exactly like write_file/delete do, so a
    # targeted edit is as revertible as any other change Mike makes.
    from brain import revert_store
    revert_store.capture(str(file))

    after = before.replace(old_text, new_text)
    try:
        previous_mtime = file.stat().st_mtime
    except OSError:
        previous_mtime = None

    try:
        file.write_text(after, encoding="utf-8")
    except OSError as exc:
        return {"status": "error", "error": f"Could not write {file}: {exc}"}

    _ensure_visible_change(file, previous_mtime)

    return {
        "status": "success",
        "path": str(file),
        "replacements": occurrences,
        "result": f"Replaced {occurrences} occurrence(s) in {file.name}.",
        "diff": _diff(before, after, file.name) or "(no textual change)",
    }


def multi_edit(path: str, edits: list[dict]) -> dict:
    """
    Apply several edits to one file atomically — all of them, or none.

    Applied in sequence against the in-memory text so later edits see earlier
    ones. If any single edit fails to match, nothing is written at all: a
    half-applied set of related changes is a broken file, and the model
    cannot easily tell which half landed.
    """
    file = resolve_path(path)

    if not file.exists():
        return {"status": "error", "error": f"No such file: {file}", "reason": NOT_FOUND}
    if not edits:
        return {"status": "error", "error": "No edits were provided."}

    try:
        before = file.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return {"status": "error", "error": f"Could not read {file}: {exc}"}

    working = before
    applied = 0

    for index, edit in enumerate(edits, start=1):
        old_text = edit.get("old_text", "")
        new_text = edit.get("new_text", "")

        if not old_text:
            return {
                "status": "error",
                "error": f"Edit {index} has empty old_text. Nothing was changed.",
            }

        count = working.count(old_text)
        if count == 0:
            return {
                "status": "error",
                "reason": NOT_FOUND,
                "failed_edit": index,
                "error": (
                    f"Edit {index} of {len(edits)} did not match anything in "
                    f"{file.name}. No edits were applied — the file is unchanged."
                ),
            }
        if count > 1 and edit.get("expect_count") is None:
            return {
                "status": "error",
                "reason": AMBIGUOUS,
                "failed_edit": index,
                "occurrences": count,
                "error": (
                    f"Edit {index} of {len(edits)} matches {count} places in "
                    f"{file.name}. No edits were applied — the file is unchanged. "
                    "Add surrounding context to make it unique."
                ),
            }

        working = working.replace(old_text, new_text)
        applied += 1

    if working == before:
        return {
            "status": "success",
            "path": str(file),
            "replacements": 0,
            "result": "Those edits produced no change to the file.",
            "diff": "",
        }

    from brain import revert_store
    revert_store.capture(str(file))

    try:
        previous_mtime = file.stat().st_mtime
    except OSError:
        previous_mtime = None

    try:
        file.write_text(working, encoding="utf-8")
    except OSError as exc:
        return {"status": "error", "error": f"Could not write {file}: {exc}"}

    _ensure_visible_change(file, previous_mtime)

    return {
        "status": "success",
        "path": str(file),
        "replacements": applied,
        "result": f"Applied {applied} edit(s) to {file.name}.",
        "diff": _diff(before, working, file.name),
    }
