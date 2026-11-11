"""Rule-based sorting: which category folder a file belongs in, and whether
its name is junk worth replacing.

These rules are the floor, not the ceiling. They run with no model at all,
so the organizer always produces a sensible plan; the local model (see
organizer/model.py) only refines names and adds a topic subfolder on top.
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

# Folder names are plain English and stable: they are what the user will see
# in Finder for years, and what undo has to find again.
CATEGORIES: dict[str, frozenset[str]] = {
    "Documents": frozenset({
        ".pdf", ".doc", ".docx", ".odt", ".rtf", ".txt", ".md", ".pages",
        ".tex", ".epub", ".mobi",
    }),
    "Spreadsheets": frozenset({".xls", ".xlsx", ".ods", ".csv", ".tsv", ".numbers"}),
    "Presentations": frozenset({".ppt", ".pptx", ".odp", ".key"}),
    "Images": frozenset({
        ".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".heif", ".bmp",
        ".tif", ".tiff", ".svg", ".raw", ".cr2", ".nef", ".arw", ".dng", ".avif",
    }),
    "Videos": frozenset({".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v", ".wmv", ".flv"}),
    "Audio": frozenset({".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".aiff"}),
    "Archives": frozenset({".zip", ".rar", ".7z", ".tar", ".gz", ".tgz", ".bz2", ".xz"}),
    "Installers": frozenset({".dmg", ".pkg", ".exe", ".msi", ".apk", ".deb", ".rpm", ".appimage"}),
    "Code": frozenset({
        ".py", ".ipynb", ".js", ".ts", ".tsx", ".jsx", ".java", ".c", ".cpp",
        ".h", ".hpp", ".cs", ".go", ".rs", ".rb", ".php", ".swift", ".kt",
        ".dart", ".m", ".sh", ".json", ".yaml", ".yml", ".toml", ".xml",
        ".html", ".css", ".sql",
    }),
    "Design & 3D": frozenset({
        ".psd", ".ai", ".fig", ".sketch", ".xd", ".blend", ".stl", ".step",
        ".stp", ".iges", ".igs", ".obj", ".fbx", ".dwg", ".dxf", ".sldprt",
        ".sldasm", ".f3d",
    }),
    "Fonts": frozenset({".ttf", ".otf", ".woff", ".woff2"}),
}

SCREENSHOTS = "Screenshots"
DUPLICATES = "Duplicates"
OTHER = "Other"

# Every folder the organizer may create at the top level. Undo and the
# planner both rely on this list to recognise their own folders.
ALL_FOLDERS = tuple(CATEGORIES) + (SCREENSHOTS, DUPLICATES, OTHER)

_SCREENSHOT_RE = re.compile(
    r"^(screen ?shot|screenshot[_ -]|cleanshot|screen recording|simulator screen shot)",
    re.IGNORECASE,
)


def category_for(name: str, suffix: str) -> str:
    if _SCREENSHOT_RE.match(name) and suffix in CATEGORIES["Images"] | CATEGORIES["Videos"]:
        return SCREENSHOTS
    for category, suffixes in CATEGORIES.items():
        if suffix in suffixes:
            return category
    return OTHER


# ── junk names ─────────────────────────────────────────────

# Names that say nothing about what the file is. Each pattern matches the
# whole stem (after a trailing copy marker is stripped).
_JUNK_PATTERNS = [
    r"(img|image|dsc|dscn|dcim|pxl|mvimg|vid|mov|photo|pic|picture)[_\- ]?\d[\d_\-]*",
    # "WhatsApp Image 2026-01-04 at 10.30.15 PM", "IMG-20260104-WA0007"
    r"whatsapp (image|video|audio|document)[\d\-_ .atpm]*",
    r"(img|vid|aud|doc|ptt)-\d{8}-wa\d+",
    r"(document|doc|untitled|new document|file|download|downloads?|scan|scanned|"
    r"export|output|attachment|unnamed|image|picture|copy)[_\- ]?\d*",
    r"\d[\d_\- .]{3,}",                       # bare numbers and dates
    r"[0-9a-f]{16,}",                         # hashes
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",  # uuids
    r"(screen ?shot|screenshot|screen recording).*",
]
_JUNK_RE = re.compile(r"^(?:" + "|".join(_JUNK_PATTERNS) + r")$", re.IGNORECASE)

# "report (1)", "report copy", "report copy 2", "report - Copy", "report(3)".
# A bare trailing number is NOT a copy marker: "Chapter 2" and "Lab 3" are
# real names, and stripping them would collide distinct files.
_COPY_MARKER_RE = re.compile(
    r"(\s*\(\d+\)|\s+-?\s*copy(\s*\d+)?)$", re.IGNORECASE
)


def strip_copy_marker(stem: str) -> str:
    stripped = _COPY_MARKER_RE.sub("", stem).strip()
    return stripped or stem


def is_junk_name(stem: str) -> bool:
    return bool(_JUNK_RE.match(strip_copy_marker(stem).strip()))


# ── safe names ─────────────────────────────────────────────

_UNSAFE_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')
_SPACES = re.compile(r"\s+")
MAX_STEM = 80
# Names Windows refuses for any file, whatever the extension ("CON.pdf" fails).
_RESERVED = re.compile(r"^(con|prn|aux|nul|com[1-9]|lpt[1-9])$", re.IGNORECASE)


def clean_stem(stem: str) -> str:
    """Make a model-suggested name safe to use as a filename on macOS and
    Windows. Returns "" when nothing usable is left."""
    stem = _UNSAFE_CHARS.sub(" ", stem)
    stem = _SPACES.sub(" ", stem).strip(" .-_")
    if len(stem) > MAX_STEM:
        stem = stem[:MAX_STEM].rsplit(" ", 1)[0].strip(" .-_") or stem[:MAX_STEM]
    if _RESERVED.match(stem):
        stem = f"{stem} file"
    return stem


def dated_stem(prefix: str, modified: float) -> str:
    """A readable fallback name for screenshots and photos with junk names:
    "Screenshot 2026-11-10 15.30" sorts by date in Finder."""
    when = datetime.fromtimestamp(modified)
    return f"{prefix} {when:%Y-%m-%d %H.%M}"


def rule_based_stem(stem: str, category: str, modified: float) -> str | None:
    """A better name without any model, or None to keep the current one.

    Only junk names are replaced. A name the user chose -- even an odd one --
    is theirs; renaming "my notes final FINAL.docx" would be presumptuous.
    The one exception is a trailing copy marker on a file that is not a
    duplicate: "resume (1).pdf" becomes "resume.pdf" when that is free.
    """
    if category == SCREENSHOTS:
        return dated_stem("Screenshot", modified)
    if is_junk_name(stem):
        if category == "Images":
            return dated_stem("Photo", modified)
        if category == "Videos":
            return dated_stem("Video", modified)
        return None  # needs the model to say what it is
    stripped = strip_copy_marker(stem)
    if stripped != stem:
        return stripped
    return None


def target_folder(root: Path, category: str, topic: str | None) -> Path:
    folder = root / category
    if topic:
        folder = folder / topic
    return folder
