"""Command line for the folder organizer.

    python -m organizer plan    <folder> [--no-ai] [--images]   preview only
    python -m organizer apply   <folder> [--no-ai] [--images] [--yes]
    python -m organizer undo    [run_id]
    python -m organizer history

`plan` never touches the folder. `apply` builds a fresh plan, shows it, and
moves nothing until it gets a "y".
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from organizer import apply_plan, build_plan, list_runs, undo_run
from organizer.plan import Plan

PREVIEW_PER_FOLDER = 8


def _progress(index: int, total: int, name: str) -> None:
    if sys.stderr.isatty():
        print(f"\r  reading {index}/{total}  {name[:50]:<50}", end="", file=sys.stderr, flush=True)
        if index == total:
            print(file=sys.stderr)


def _build(args) -> Plan | None:
    print(f"Looking at {Path(args.folder).expanduser()} ...")
    try:
        return build_plan(args.folder, use_model=not args.no_ai, look_at_images=args.images,
                          progress=_progress)
    except (NotADirectoryError, ValueError) as exc:
        print(exc)
        return None


def print_plan(plan: Plan, *, full: bool = False) -> None:
    for note in plan.notes:
        print(f"  note: {note}")
    if not plan.moves:
        print("\nNothing to organize. This folder is already tidy.")
    else:
        print()
        for folder, moves in plan.by_folder().items():
            print(f"{folder}/  ({len(moves)})")
            shown = moves if full else moves[:PREVIEW_PER_FOLDER]
            for m in shown:
                if m.renamed:
                    why = f"   [{m.reason}]" if m.reason else ""
                    print(f"    {m.src.name}  ->  {m.dst.name}{why}")
                elif m.reason:
                    print(f"    {m.src.name}   [{m.reason}]")
                else:
                    print(f"    {m.src.name}")
            if len(moves) > len(shown):
                print(f"    ... and {len(moves) - len(shown)} more")
    if plan.skipped:
        print(f"\nLeft alone ({len(plan.skipped)}):")
        for path, why in plan.skipped[:PREVIEW_PER_FOLDER]:
            print(f"    {path.name}   [{why}]")
        if len(plan.skipped) > PREVIEW_PER_FOLDER:
            print(f"    ... and {len(plan.skipped) - PREVIEW_PER_FOLDER} more")
    print(f"\n{len(plan.moves)} files to move, {plan.renamed_count} renamed, "
          f"{plan.duplicate_count} duplicates set aside. Nothing is deleted.")


def cmd_plan(args) -> int:
    plan = _build(args)
    if plan is None:
        return 1
    print_plan(plan, full=args.full)
    return 0


def cmd_apply(args) -> int:
    plan = _build(args)
    if plan is None:
        return 1
    print_plan(plan, full=args.full)
    if not plan.moves:
        return 0
    if not args.yes:
        answer = input("\nOrganize these files? You can undo this later. [y/N] ").strip().lower()
        if answer not in ("y", "yes"):
            print("Nothing was moved.")
            return 1
    result = apply_plan(plan)
    print(f"\nMoved {result.moved} files. Undo with: python -m organizer undo {result.run_id}")
    for path, why in result.failed:
        print(f"  not moved: {Path(path).name}  [{why}]")
    return 0 if not result.failed else 2


def cmd_undo(args) -> int:
    try:
        result = undo_run(args.run_id)
    except LookupError as exc:
        print(exc)
        return 1
    except FileNotFoundError:
        print(f"No run called {args.run_id}.")
        return 1
    print(f"Put {result.restored} files back.")
    if result.already_back:
        print(f"{result.already_back} were already in their original place.")
    for path, why in result.left_alone:
        print(f"  left alone: {Path(path).name}  [{why}]")
    return 0 if not result.left_alone else 2


def cmd_history(_args) -> int:
    runs = list_runs()
    if not runs:
        print("No organize runs yet.")
    for r in runs:
        print(f"{r['run_id']}  {r['state']:<14} {r['moves']:>5} files  {r['root']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m organizer",
                                     description="Tidy a messy folder, privately. Nothing is deleted.")
    sub = parser.add_subparsers(dest="command", required=True)

    for name, func, helptext in (("plan", cmd_plan, "preview what would happen"),
                                 ("apply", cmd_apply, "organize the folder (asks first)")):
        p = sub.add_parser(name, help=helptext)
        p.add_argument("folder")
        p.add_argument("--no-ai", action="store_true", help="sort by rules only, skip the local model")
        p.add_argument("--images", action="store_true", help="let the model look at images (slower)")
        p.add_argument("--full", action="store_true", help="list every file, not a sample")
        if name == "apply":
            p.add_argument("--yes", action="store_true", help="don't ask for confirmation")
        p.set_defaults(func=func)

    u = sub.add_parser("undo", help="put every file from a run back")
    u.add_argument("run_id", nargs="?")
    u.set_defaults(func=cmd_undo)

    h = sub.add_parser("history", help="list past runs")
    h.set_defaults(func=cmd_history)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
