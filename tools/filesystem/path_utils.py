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

    return Path(path).expanduser().resolve()