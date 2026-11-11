"""Find the files in a folder that are safe to organize.

v1 looks only at the folder's own top level. Subfolders the user already made
are their organisation and are left exactly as they are -- tidying inside
someone's existing structure is a different, riskier feature.
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from pathlib import Path

# Still being written by a browser or another app. Moving one of these breaks
# the download that owns it.
PARTIAL_SUFFIXES = frozenset({
    ".crdownload", ".part", ".partial", ".download", ".tmp", ".opdownload",
})

# A file touched this recently may still be mid-write (a save, a copy, an
# export). Leave it for the next run rather than moving it out from under
# whatever is writing it.
RECENT_SECONDS = 60

# Files Windows (and Finder) keep in folders for themselves. They don't start
# with a dot, so the dotfile rule misses them; moving desktop.ini breaks the
# folder's own look and name. Never shown, never moved.
SYSTEM_FILE_NAMES = frozenset({
    "desktop.ini", "thumbs.db", "ehthumbs.db", "ehthumbs_vista.db", "icon\r",
})

# Shortcuts. A Desktop is mostly app shortcuts; sweeping them into "Other"
# would wreck it. They are the user's launchers, not clutter.
SHORTCUT_SUFFIXES = frozenset({".lnk", ".url", ".webloc", ".desktop"})

# Windows file attributes (stat().st_file_attributes).
_HIDDEN, _SYSTEM = 0x2, 0x4
# A OneDrive "online-only" file: its contents are not on this computer, and
# reading them makes OneDrive download the file. Windows 11 backs up the
# Desktop to OneDrive by default, so a Desktop can be full of these.
_CLOUD_ONLY = 0x1000 | 0x40000 | 0x400000   # OFFLINE | RECALL_ON_OPEN | RECALL_ON_DATA_ACCESS


def _attributes(stat) -> int:
    return getattr(stat, "st_file_attributes", 0) or 0


@dataclass
class FileEntry:
    path: Path
    size: int
    modified: float
    # Contents live in the cloud: moving is fine, reading is not (it would
    # download the file). Never hashed for duplicates, never read by the model.
    cloud_only: bool = False
    suffix: str = field(init=False)

    def __post_init__(self) -> None:
        self.suffix = self.path.suffix.lower()

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def stem(self) -> str:
        return self.path.stem


@dataclass
class ScanResult:
    root: Path
    files: list[FileEntry]
    # (path, reason) -- reported back so the preview can say why a file was
    # left alone instead of it silently not appearing.
    skipped: list[tuple[Path, str]]


# A folder holding one of these is a project: its files reference each other
# by name, and sorting them into "Code" and "Documents" breaks it.
PROJECT_MARKERS = (".git", ".hg", ".svn", "package.json", "pyproject.toml", "setup.py",
                   "Cargo.toml", "go.mod", "pom.xml", "build.gradle", "Makefile",
                   "CMakeLists.txt")

_SYSTEM_ROOTS = ("/System", "/Library", "/Applications", "/usr", "/bin", "/sbin", "/etc",
                 "/private/etc", "C:\\Windows", "C:\\Program Files",
                 "C:\\Program Files (x86)", "C:\\ProgramData")


def refusal(root: Path) -> str | None:
    """Why this folder must not be organized, or None if it's fine."""
    home = Path.home().resolve()
    if root == Path(root.anchor) or root == home:
        return (f"{root} is too broad to organize: pick a folder inside it, "
                "like Downloads or Desktop.")
    if root == home / "Library" or (home / "Library") in root.parents:
        return f"{root} is where apps keep their data; the organizer leaves it alone."
    for system in map(Path, _SYSTEM_ROOTS):
        if root == system or system in root.parents:
            return f"{root} is a system folder; the organizer leaves those alone."
    for marker in PROJECT_MARKERS:
        if (root / marker).exists():
            return (f"{root} looks like a project ({marker}); moving its files would "
                    "break it, so the organizer leaves it alone.")
    return None


def scan(folder: str | Path, *, now: float | None = None) -> ScanResult:
    root = Path(folder).expanduser().resolve()
    if not root.is_dir():
        raise NotADirectoryError(f"Not a folder: {root}")
    refused = refusal(root)
    if refused:
        raise ValueError(refused)

    now = time.time() if now is None else now
    files: list[FileEntry] = []
    skipped: list[tuple[Path, str]] = []

    for entry in sorted(root.iterdir(), key=lambda p: p.name.lower()):
        name = entry.name
        if name.startswith(".") or name.lower() in SYSTEM_FILE_NAMES:
            # .DS_Store, .localized, desktop.ini, Thumbs.db -- system state.
            continue
        if entry.is_symlink():
            skipped.append((entry, "shortcut (symlink)"))
            continue
        if entry.is_dir():
            # Includes .app bundles, which are directories on macOS.
            continue
        if not entry.is_file():
            continue
        if entry.suffix.lower() in PARTIAL_SUFFIXES:
            skipped.append((entry, "unfinished download"))
            continue
        if entry.suffix.lower() in SHORTCUT_SUFFIXES:
            skipped.append((entry, "shortcut"))
            continue
        try:
            stat = entry.stat()
        except OSError as exc:
            skipped.append((entry, f"unreadable ({exc.strerror or exc})"))
            continue
        attributes = _attributes(stat)
        if attributes & (_HIDDEN | _SYSTEM):
            # Windows' own hidden and system files: not the user's clutter.
            continue
        if now - stat.st_mtime < RECENT_SECONDS:
            skipped.append((entry, "changed in the last minute"))
            continue
        files.append(FileEntry(path=entry, size=stat.st_size, modified=stat.st_mtime,
                               cloud_only=bool(attributes & _CLOUD_ONLY)))

    return ScanResult(root=root, files=files, skipped=skipped)


def content_hash(path: Path, chunk: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(chunk):
            digest.update(block)
    return digest.hexdigest()


def find_duplicates(files: list[FileEntry]) -> dict[Path, Path]:
    """Map each duplicate file to the copy that is kept.

    Only files with an identical size are hashed, so a folder of thousands of
    distinct files costs almost nothing. The copy kept is the one with the
    most readable name ("report.pdf" over "report (1).pdf"), then the oldest.
    Empty files are never treated as duplicates of each other -- they carry
    no content to be duplicated.
    """
    from organizer.classify import is_junk_name, strip_copy_marker

    by_size: dict[int, list[FileEntry]] = {}
    for f in files:
        # An online-only file would be downloaded just to hash it.
        if f.size > 0 and not f.cloud_only:
            by_size.setdefault(f.size, []).append(f)

    duplicates: dict[Path, Path] = {}
    for group in by_size.values():
        if len(group) < 2:
            continue
        by_hash: dict[str, list[FileEntry]] = {}
        for f in group:
            try:
                by_hash.setdefault(content_hash(f.path), []).append(f)
            except OSError:
                continue
        for same in by_hash.values():
            if len(same) < 2:
                continue
            same.sort(key=lambda f: (
                strip_copy_marker(f.stem) != f.stem,  # "x (1)" loses to "x"
                is_junk_name(f.stem),
                f.modified,
            ))
            keeper = same[0]
            for dup in same[1:]:
                duplicates[dup.path] = keeper.path
    return duplicates
