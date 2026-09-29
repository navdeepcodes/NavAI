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


# ── a file open in the student's editor ──────────────────────────────────
#
# Its text there is the truth: it may hold changes not saved yet. Edited on
# disk, Mike changed the older text and the editor then held two versions --
# the student's unsaved work, or Mike's change, was lost. So an open file is
# read from the editor and edited through it (ide/manager.py): the change
# lands in the student's buffer, is saved, Ctrl+Z undoes it, and the editor's
# own checker says what it thinks of the result.

def _editor_text(file: Path) -> str | None:
    """The file's text in the connected editor, unsaved changes included --
    None when no editor has it open, and the disk is the truth."""
    try:
        from ide import manager
        return manager.editor_text(str(file))
    except Exception:
        return None


def _position(text: str, offset: int) -> tuple[int, int]:
    """(line, column) at `offset`, 0-based, the column in UTF-16 units as
    editors count it."""
    line = text.count("\n", 0, offset)
    start = text.rfind("\n", 0, offset) + 1
    return line, len(text[start:offset].encode("utf-16-le")) // 2


def _write_through_editor(file: Path, before: str, after: str) -> dict | None:
    """before -> after as one replacement of the part that changed, applied by
    the editor. Its answer (ok, problems, changed), or None when no editor
    holds the file any more."""
    from ide import manager
    head = 0
    limit = min(len(before), len(after))
    while head < limit and before[head] == after[head]:
        head += 1
    tail = 0
    while tail < limit - head and before[-1 - tail] == after[-1 - tail]:
        tail += 1
    return manager.replace_in_editor(
        str(file), _position(before, head), _position(before, len(before) - tail),
        before[head:len(before) - tail], after[head:len(after) - tail])


def _problems(file: Path, problems: list[dict]) -> str:
    if not problems:
        return f"VS Code shows no errors or warnings in {file.name} after this edit."
    shown = [f"- line {p.get('line')}: {p.get('severity')}: {p.get('message')}"
             + (f" [{p['source']}]" if p.get("source") else "") for p in problems[:10]]
    return f"VS Code shows these in {file.name} after this edit:\n" + "\n".join(shown)


#: After a write to disk, how long VS Code's checkers get to look at the
#: files: a warm language server answers in about a second (measured: three
#: files, 1.0s); a clean file usually says nothing at all, so this is also the
#: most a clean write waits. check_syntax waits longer when asked.
EDITOR_CHECK_SECONDS = 2.5
#: At most this many files checked (and opened as tabs) per write.
EDITOR_CHECK_MAX = 10


def _checked_in_editor(files: list[Path]) -> dict[str, dict] | None:
    """What the student's VS Code says about files just written to disk --
    {path: {"reported", "problems"}} for those in a project it has open, so
    a broken file is known at the step that broke it. Each opens as a tab
    behind the one they're on: it's what VS Code checks, and it's the work."""
    try:
        from ide import manager
        return manager.problems_for([str(f) for f in files[:EDITOR_CHECK_MAX]],
                                    wait=EDITOR_CHECK_SECONDS)
    except Exception:
        return None


def _note_editor_check(result: dict, file: Path) -> dict:
    """Add VS Code's word on one file written to disk to its result."""
    found = _checked_in_editor([file])
    info = next(iter(found.values()), None) if found else None
    if info and (info["problems"] or info["reported"]):
        result["problems"] = _problems(file, info["problems"])
    return result


def _finish_in_editor(file: Path, before: str, after: str, result: dict) -> dict | None:
    """Write through the editor holding the file. The finished tool result, or
    None when no editor holds it and the disk should be written instead."""
    outcome = _write_through_editor(file, before, after)
    if outcome is None or outcome.get("open") is False:
        return None
    if not outcome.get("ok"):
        if outcome.get("changed"):
            error = ("The file changed in the editor while I was editing it, so nothing "
                     "was changed. Read it again and redo the edit.")
        else:
            error = (f"The editor couldn't apply the edit ({outcome.get('error') or 'no reason given'}). "
                     "Nothing was changed.")
        return {"status": "error", "error": error}
    result["editor"] = "Applied in the editor and saved; Ctrl+Z there undoes it."
    result["problems"] = _problems(file, outcome.get("problems") or [])
    return result


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

    text = _editor_text(file)          # what the student sees, unsaved changes too
    if text is None:
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


#: read_files: at most this many files, and this much text in all -- several
#: whole files at once is the point, a context window's worth is not.
READ_FILES_MAX = 8
READ_FILES_BUDGET = 60_000
WRITE_FILES_MAX = 20


def read_files(paths: list[str]) -> dict:
    """Several files at once, each numbered as read_lines numbers it (and read
    from the editor when it's open there). One step instead of one per file:
    every step re-sends the conversation, so reading a task's files one by one
    cost a model call -- and the allowance -- each."""
    if not paths:
        return {"status": "error", "error": "No paths were given."}
    wanted = [str(p) for p in paths if str(p).strip()]
    files, left = [], READ_FILES_BUDGET
    for path in wanted[:READ_FILES_MAX]:
        if left <= 0:
            files.append({"path": path, "skipped": "Not read: the others filled this read. Read it next."})
            continue
        got = read_lines(path, 1, 400)
        if got.get("status") != "success":
            files.append({"path": path, "error": got.get("error")})
            continue
        content = got["content"]
        entry = {"path": got["path"], "total_lines": got["total_lines"], "shown": got["shown"]}
        if len(content) > left:
            content = content[:left].rsplit("\n", 1)[0]
            entry["shown"] = f"1-{content.count(chr(10)) + 1}"
            entry["truncated"] = True
        elif got.get("truncated"):
            entry["truncated"] = True
        entry["content"] = content
        left -= len(content)
        files.append(entry)
    result = {"status": "success", "files": files}
    if len(wanted) > READ_FILES_MAX:
        result["note"] = (f"Read the first {READ_FILES_MAX} of {len(wanted)}; ask for the rest "
                          "in another read_files.")
    if any(f.get("truncated") for f in files):
        result["note"] = ((result.get("note", "") + " ").lstrip()
                          + "Some files were cut short: read_lines reads the rest by line.")
    return result


def write_files(files: list[dict]) -> dict:
    """Create or replace several whole files: a new project, or a feature's
    new files, in one step. Each file goes through the editor when it's open
    there (so unsaved work isn't clobbered from behind and Ctrl+Z undoes it),
    otherwise to disk; each can be undone from Mike's activity."""
    entries = [f for f in (files or []) if isinstance(f, dict) and str(f.get("path") or "").strip()]
    if not entries:
        return {"status": "error", "error": "No files were given."}
    if len(entries) > WRITE_FILES_MAX:
        return {"status": "error",
                "error": f"That's {len(entries)} files; write at most {WRITE_FILES_MAX} at a time."}
    from brain import revert_store

    written, results = [], []
    for entry in entries:
        file = resolve_path(str(entry["path"]))
        content = str(entry.get("content") or "")
        if file.is_dir():
            results.append({"path": str(file), "error": "That's a folder, not a file."})
            continue
        existed = file.exists()
        try:
            if existed:
                from tools.filesystem.file_manager import refuse_non_text
                refuse_non_text(file)
                revert_store.capture(str(file))
            live = _editor_text(file) if existed else None
            if live is not None:
                done = _finish_in_editor(file, live, content, {"status": "success"})
                if done is not None:
                    if done.get("status") != "success":
                        results.append({"path": str(file), "error": done.get("error")})
                        continue
                    results.append({"path": str(file), "replaced": True, "editor": True,
                                    "problems": done.get("problems")})
                    written.append(file)
                    continue
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text(content, encoding="utf-8")
            results.append({"path": str(file), "replaced": existed,
                            "lines": len(content.splitlines())})
            written.append(file)
        except (OSError, ValueError) as exc:
            results.append({"path": str(file), "error": str(exc)})
    # Written through the editor, a file already has VS Code's word on it.
    on_disk = [r for r in results if not r.get("error") and not r.get("editor")]
    checked = _checked_in_editor([Path(r["path"]) for r in on_disk]) if on_disk else None
    editor_note = {}
    if checked:
        for r in on_disk:
            info = checked.get(r["path"])
            if info and (info["problems"] or info["reported"]):
                r["problems"] = _problems(Path(r["path"]), info["problems"])
        quiet = [Path(p).name for p, i in checked.items() if not i["problems"] and not i["reported"]]
        if quiet:
            editor_note["editor_check"] = (
                f"VS Code reported nothing on {', '.join(quiet)} within "
                f"{EDITOR_CHECK_SECONDS:g}s -- a clean file usually says nothing, but a slow "
                "checker can too.")
    failed = [r for r in results if r.get("error")]
    summary = f"Wrote {len(written)} of {len(entries)} file(s)."
    if failed:
        summary += f" {len(failed)} failed; the others were written."
    return {"status": "success" if written else "error", "result": summary, "files": results,
            **editor_note, **({"error": summary} if not written else {})}


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
    try:
        from tools.filesystem.file_manager import refuse_non_text
        refuse_non_text(file)
    except ValueError as exc:
        return {"status": "error", "error": str(exc)}

    if not old_text:
        return {
            "status": "error",
            "error": "old_text must not be empty. To create or overwrite a whole file, use write_file.",
        }

    live = _editor_text(file)
    try:
        before = live if live is not None else file.read_text(encoding="utf-8")
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
    result = {
        "status": "success",
        "path": str(file),
        "replacements": occurrences,
        "result": f"Replaced {occurrences} occurrence(s) in {file.name}.",
        "diff": _diff(before, after, file.name) or "(no textual change)",
    }
    if live is not None:
        done = _finish_in_editor(file, before, after, result)
        if done is not None:
            return done

    try:
        previous_mtime = file.stat().st_mtime
    except OSError:
        previous_mtime = None

    try:
        file.write_text(after, encoding="utf-8")
    except OSError as exc:
        return {"status": "error", "error": f"Could not write {file}: {exc}"}

    _ensure_visible_change(file, previous_mtime)
    return _note_editor_check(result, file)


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

    live = _editor_text(file)
    try:
        before = live if live is not None else file.read_text(encoding="utf-8")
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

    result = {
        "status": "success",
        "path": str(file),
        "replacements": applied,
        "result": f"Applied {applied} edit(s) to {file.name}.",
        "diff": _diff(before, working, file.name),
    }
    if live is not None:
        done = _finish_in_editor(file, before, working, result)
        if done is not None:
            return done

    try:
        previous_mtime = file.stat().st_mtime
    except OSError:
        previous_mtime = None

    try:
        file.write_text(working, encoding="utf-8")
    except OSError as exc:
        return {"status": "error", "error": f"Could not write {file}: {exc}"}

    _ensure_visible_change(file, previous_mtime)
    return _note_editor_check(result, file)
