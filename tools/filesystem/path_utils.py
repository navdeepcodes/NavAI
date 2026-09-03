from pathlib import Path


HOME = Path.home()

DESKTOP = HOME / "Desktop"

DOWNLOADS = HOME / "Downloads"

DOCUMENTS = HOME / "Documents"

PICTURES = HOME / "Pictures"

MOVIES = HOME / "Movies"

MUSIC = HOME / "Music"


SPECIAL_PATHS = {

    "desktop": DESKTOP,

    "downloads": DOWNLOADS,

    "documents": DOCUMENTS,

    "pictures": PICTURES,

    "movies": MOVIES,

    "music": MUSIC,

    "home": HOME

}


def resolve_path(path: str) -> Path:

    """
    Converts natural folder names into absolute paths.

    Example:

    Desktop

    Downloads/Rocket

    Documents/College
    """

    path = path.strip()

    lower = path.lower()

    for key, value in SPECIAL_PATHS.items():

        if lower == key:

            return value

        if lower.startswith(key + "/"):

            remaining = path[len(key):].lstrip("/")

            return value / remaining

    expanded = Path(path).expanduser()

    if expanded.is_absolute():

        return expanded.resolve()

    # Anything else relative is relative to home, matching what Mike is told
    # ("paths like Desktop/folder are relative to home"). Resolving against
    # the process working directory instead would silently write the user's
    # files into Mike's own source tree.
    return (HOME / expanded).resolve()