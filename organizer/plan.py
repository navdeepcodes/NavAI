"""Turn a scanned folder into an exact list of moves -- the plan the user
approves before anything happens.

A plan is complete and final: every destination is decided here, including
collision suffixes, so what the preview shows is precisely what apply does.
Building a plan touches nothing on disk.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from organizer import classify
from organizer.scan import FileEntry, find_duplicates, scan

# A topic subfolder holding a single file is clutter, not organisation.
MIN_FILES_PER_TOPIC = 2

Progress = Callable[[int, int, str], None]


@dataclass
class Move:
    src: Path
    dst: Path
    category: str
    topic: str | None = None
    renamed: bool = False
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "src": str(self.src), "dst": str(self.dst), "category": self.category,
            "topic": self.topic, "renamed": self.renamed, "reason": self.reason,
        }


@dataclass
class Plan:
    root: Path
    moves: list[Move] = field(default_factory=list)
    skipped: list[tuple[Path, str]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    used_model: bool = False

    @property
    def renamed_count(self) -> int:
        return sum(1 for m in self.moves if m.renamed)

    @property
    def duplicate_count(self) -> int:
        return sum(1 for m in self.moves if m.category == classify.DUPLICATES)

    def by_folder(self) -> dict[str, list[Move]]:
        """Moves grouped by the folder they land in, relative to the root --
        the shape the preview is drawn in."""
        groups: dict[str, list[Move]] = {}
        for move in self.moves:
            groups.setdefault(str(move.dst.parent.relative_to(self.root)), []).append(move)
        return dict(sorted(groups.items()))

    def to_dict(self) -> dict:
        return {
            "root": str(self.root),
            "moves": [m.to_dict() for m in self.moves],
            "skipped": [[str(p), why] for p, why in self.skipped],
            "notes": list(self.notes),
            "used_model": self.used_model,
        }


@dataclass
class _Decision:
    entry: FileEntry
    category: str
    stem: str
    topic: str | None
    reason: str


def build_plan(folder: str | Path, *, use_model: bool = True, look_at_images: bool = False,
               progress: Progress | None = None, namer=None) -> Plan:
    result = scan(folder)
    root = result.root
    plan = Plan(root=root, skipped=list(result.skipped))

    if namer is None and use_model:
        from organizer.model import ModelNamer

        namer = ModelNamer(look_at_images=look_at_images)
    if namer is not None:
        reason = namer.unavailable_reason()
        if reason:
            plan.notes.append(reason)
            namer = None
    plan.used_model = namer is not None

    duplicates = find_duplicates(result.files)
    decisions: list[_Decision] = []
    total = len(result.files)

    for index, entry in enumerate(result.files, start=1):
        if progress:
            progress(index, total, entry.name)

        if entry.path in duplicates:
            keeper = duplicates[entry.path]
            decisions.append(_Decision(
                entry, classify.DUPLICATES, entry.stem, None,
                f"exact copy of {keeper.name}",
            ))
            continue

        category = classify.category_for(entry.name, entry.suffix)
        stem = entry.stem
        topic: str | None = None
        reason = ""

        junk = classify.is_junk_name(stem)
        suggestion = None
        if namer is not None and namer.wants(category):
            suggestion = namer.suggest(entry, category)

        # Cleaned again here, not only in model._parse: whatever produced the
        # suggestion, a "/" in it must never become a folder the user didn't ask for.
        title = classify.clean_stem(suggestion.title or "") if suggestion else ""
        topic_name = classify.clean_stem(suggestion.topic or "") if suggestion else ""
        if topic_name and category in ("Documents", "Spreadsheets", "Presentations"):
            topic = topic_name

        # Only a junk name is ever replaced. A name the user typed is theirs,
        # even when the model thinks it could do better.
        if junk and title:
            stem, reason = title, "named from its contents"
        else:
            fallback = classify.rule_based_stem(stem, category, entry.modified)
            if fallback and fallback != stem:
                stem = fallback
                reason = "dated name" if junk or category == classify.SCREENSHOTS else "removed copy marker"

        decisions.append(_Decision(entry, category, stem, topic, reason))

    _prune_small_topics(decisions)
    plan.moves = _resolve_destinations(root, decisions, plan.skipped)
    return plan


def _prune_small_topics(decisions: list[_Decision]) -> None:
    counts = Counter((d.category, d.topic) for d in decisions if d.topic)
    for d in decisions:
        if d.topic and counts[(d.category, d.topic)] < MIN_FILES_PER_TOPIC:
            d.topic = None


def _resolve_destinations(root: Path, decisions: list[_Decision],
                          skipped: list[tuple[Path, str]]) -> list[Move]:
    """Pick a final, unique destination for every file.

    Names are compared case-insensitively: macOS and Windows filesystems are,
    so "Report.pdf" and "report.pdf" are the same place there. A destination
    is free only if no existing file sits there AND no earlier move in this
    plan has already claimed it.
    """
    claimed: set[str] = set()
    placed: list[tuple[int, Move]] = []

    # Files keeping their own name claim it first. Otherwise "note (1).txt"
    # (which sorts before "note.txt") took "note.txt" by dropping its copy
    # marker, and the user's original was pushed aside to "note 2.txt".
    order = sorted(range(len(decisions)),
                   key=lambda i: decisions[i].stem != decisions[i].entry.stem)

    for i in order:
        d = decisions[i]
        folder = classify.target_folder(root, d.category, d.topic)
        blocked = _blocked_by_file(root, folder)
        if blocked is not None:
            skipped.append((d.entry.path, f"'{blocked.name}' exists as a file, not a folder"))
            continue

        suffix = d.entry.path.suffix  # original case, always kept
        if d.reason == "removed copy marker" and _taken(
                folder / f"{d.stem}{suffix}", claimed, d.entry.path):
            # The clean name belongs to another file. "note 2.txt" would be a
            # rename for nothing; keeping "note (1).txt" says what it is.
            d.stem, d.reason = d.entry.stem, ""
        dst = _free_path(folder, d.stem, suffix, claimed, src=d.entry.path)
        if dst == d.entry.path:
            continue
        claimed.add(str(dst).casefold())
        renamed = dst.stem != d.entry.stem
        placed.append((i, Move(
            src=d.entry.path, dst=dst, category=d.category, topic=d.topic,
            renamed=renamed, reason=d.reason if renamed or d.category == classify.DUPLICATES else "",
        )))
    # Back in folder order, so the preview reads alphabetically.
    return [move for _, move in sorted(placed, key=lambda pair: pair[0])]


def _blocked_by_file(root: Path, folder: Path) -> Path | None:
    current = root
    for part in folder.relative_to(root).parts:
        current = current / part
        if current.exists() and not current.is_dir():
            return current
    return None


def _free_path(folder: Path, stem: str, suffix: str, claimed: set[str], *, src: Path) -> Path:
    candidate = folder / f"{stem}{suffix}"
    n = 2
    while _taken(candidate, claimed, src):
        candidate = folder / f"{stem} {n}{suffix}"
        n += 1
    return candidate


def _taken(path: Path, claimed: set[str], src: Path) -> bool:
    if str(path).casefold() in claimed:
        return True
    if path.exists() or path.is_symlink():
        # The file's own current location is not a conflict with itself.
        try:
            return not path.samefile(src)
        except OSError:
            return True
    return False
