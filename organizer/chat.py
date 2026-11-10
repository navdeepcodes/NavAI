"""The organizer as Mike's chat tools: preview, apply, undo.

    preview_organize(folder)   read-only. Builds the plan, keeps it here under
                               an id, and returns a summary for the model.
    apply_organize(plan_id)    gated. The confirmation shows the moves of THIS
                               stored plan, and exactly those moves are made --
                               what the user approved is what happens, not a
                               fresh plan built after they said yes.
    undo_organize(run_id?)     gated. Puts a run's files back.

The model never chooses a destination. It can only name a folder to look at,
and pass back an id this module handed out.
"""
from __future__ import annotations

import itertools
import time
from dataclasses import dataclass
from pathlib import Path

from organizer import apply_plan, build_plan, list_runs, undo_run
from organizer import classify
from organizer.plan import Plan

#: A stored plan older than this is refused: the folder has had time to change
#: under it, and the user should look at a fresh preview.
PLAN_TTL_SECONDS = 15 * 60
_MAX_PLANS = 5
SAMPLE_PER_FOLDER = 4


@dataclass
class _Stored:
    plan: Plan
    made_at: float


_plans: dict[str, _Stored] = {}
_ids = itertools.count(1)


def _short(path: Path | str) -> str:
    path = Path(path)
    try:
        return "~/" + str(path.relative_to(Path.home()))
    except ValueError:
        return str(path)


def _store(plan: Plan) -> str:
    plan_id = f"plan-{next(_ids)}"
    _plans[plan_id] = _Stored(plan, time.time())
    while len(_plans) > _MAX_PLANS:
        _plans.pop(next(iter(_plans)))
    return plan_id


def stored_plan(plan_id: str) -> Plan | None:
    stored = _plans.get(str(plan_id or ""))
    if stored is None or time.time() - stored.made_at > PLAN_TTL_SECONDS:
        return None
    return stored.plan


# ── what the user and the model see ──────────────────────

def summary_line(plan: Plan) -> str:
    folders = {m.dst.parent for m in plan.moves}
    return (f"{len(plan.moves)} files into {len(folders)} folders, "
            f"{plan.renamed_count} renamed, {plan.duplicate_count} duplicates set aside")


def describe(plan: Plan, *, sample: int = SAMPLE_PER_FOLDER) -> list[str]:
    lines = []
    for folder, moves in plan.by_folder().items():
        lines.append(f"{folder}/ ({len(moves)})")
        for m in moves[:sample]:
            if m.renamed:
                lines.append(f"  {m.src.name} -> {m.dst.name}")
            elif m.reason:
                lines.append(f"  {m.src.name} [{m.reason}]")
            else:
                lines.append(f"  {m.src.name}")
        if len(moves) > sample:
            lines.append(f"  ... and {len(moves) - sample} more")
    return lines


def confirmation_text(plan_id: str) -> str:
    plan = stored_plan(plan_id)
    if plan is None:
        return ("Organize a folder -- but this preview has expired or doesn't exist, "
                "so nothing will be moved.")
    lines = [f"Organize {_short(plan.root)}: {summary_line(plan)}.", ""]
    lines += describe(plan, sample=3)
    if plan.skipped:
        lines += ["", f"Left alone: {len(plan.skipped)} files."]
    lines += ["", "Nothing is deleted. You can undo the whole run in one step."]
    return "\n".join(lines)


# ── the tools ────────────────────────────────────────────

def preview(folder: str, *, use_ai: bool = True) -> dict:
    if not str(folder or "").strip():
        return {"status": "error", "retry_safe": True,
                "error": "Say which folder to organize, e.g. ~/Downloads."}
    try:
        # "Downloads", "~/Desktop", "Desktop/Screenshots" or a full path: the
        # same resolution every file tool uses (Windows' real Desktop when
        # OneDrive has moved it), never a path relative to Mike's own folder.
        from tools.filesystem.path_utils import resolve_path

        plan = build_plan(resolve_path(str(folder)), use_model=use_ai)
    except (NotADirectoryError, FileNotFoundError):
        return {"status": "error", "retry_safe": True,
                "error": f"{folder} isn't a folder. Check the path, e.g. ~/Downloads."}
    except PermissionError:
        return {"status": "error", "retry_safe": False,
                "error": (f"Mike isn't allowed to read {folder}. On a Mac, allow it in "
                          "System Settings → Privacy & Security → Files and Folders.")}
    except ValueError as exc:            # a folder the organizer refuses to touch
        return {"status": "error", "retry_safe": False, "error": str(exc)}

    if not plan.moves:
        return {"status": "success",
                "result": f"{_short(plan.root)} is already tidy: nothing to move.",
                "notes": plan.notes}

    plan_id = _store(plan)
    return {
        "status": "success",
        "plan_id": plan_id,
        "folder": _short(plan.root),
        "summary": summary_line(plan),
        "preview": describe(plan),
        "left_alone": len(plan.skipped),
        # Spelled out, so a count or a "these are copies" is read, not inferred
        # from file names that merely look alike.
        "duplicates": [f"{m.src.name} ({m.reason})" for m in plan.moves
                       if m.category == classify.DUPLICATES] or "none",
        "notes": plan.notes,
        "note": ("Nothing has moved yet. Tell the user in a sentence or two what would "
                 "change and ask whether to go ahead. Every number and file name you "
                 "mention comes from this result, never from what names suggest. When "
                 "they say yes, call apply_organize with this plan_id; its approval "
                 "window shows them the full list. Nothing has been done, so there is "
                 "nothing to undo."),
    }


def apply(plan_id: str) -> dict:
    plan = stored_plan(plan_id)
    if plan is None:
        return {"status": "error", "retry_safe": True,
                "error": "That preview has expired or doesn't exist. Run preview_organize "
                         "again so the user sees the folder as it is now."}
    _plans.pop(plan_id, None)            # a plan is applied once
    result = apply_plan(plan)
    out = {
        "status": "success" if result.moved else "error",
        "run_id": result.run_id,
        "result": f"Moved {result.moved} of {len(plan.moves)} files in {_short(plan.root)}.",
        "undo": ("undo_organize puts every file back. Let the user know you can put "
                 "everything back in one step if they change their mind."),
    }
    if result.failed:
        out["not_moved"] = [f"{Path(p).name}: {why}" for p, why in result.failed[:10]]
    return out


def undoable(run_id: str | None = None) -> dict | None:
    """The run an undo would reverse (the most recent one by default), or None
    when nothing that moved files is waiting to be undone."""
    runs = [r for r in list_runs() if r["state"] != "undone"]
    if run_id:
        return next((r for r in runs if r["run_id"] == run_id), None)
    return runs[0] if runs else None


def undo(run_id: str | None = None) -> dict:
    if undoable(run_id) is None:
        # Not a failure: it's the true state, said plainly, so the model can
        # tell the user rather than retry or apologise for an error.
        return {"status": "success", "moved": 0,
                "result": ("Nothing to undo: no files have been moved by an organize run "
                           "that's still in place (a preview moves nothing).")}
    try:
        result = undo_run(run_id or None)
    except LookupError as exc:
        return {"status": "error", "retry_safe": False, "error": str(exc)}
    except FileNotFoundError:
        return {"status": "error", "retry_safe": False,
                "error": f"No organize run called {run_id}."}
    out = {"status": "success", "result": f"Put {result.restored} files back."}
    if result.already_back:
        out["already_back"] = result.already_back
    if result.left_alone:
        out["left_alone"] = [f"{Path(p).name}: {why}" for p, why in result.left_alone[:10]]
    return out


def undo_confirmation_text(run_id: str | None) -> str:
    run = undoable(run_id)
    if run is None:
        return "Undo an organize run -- but there's no matching run, so nothing will move."
    return (f"Undo organizing {_short(run['root'])} ({run['created_at'].replace('T', ' ')}): "
            f"put {run['moves']} files back where they were.\n"
            "Files you have moved since are left where they are; nothing is overwritten.")
