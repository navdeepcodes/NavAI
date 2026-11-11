import sys
from pathlib import Path


HOME = Path.home()


def _known_folder(guid: str) -> Path | None:
    """Where Windows really keeps a user folder, or None.

    HOME / "Desktop" is wrong on many Windows 11 PCs: OneDrive backup moves
    Desktop, Documents and Pictures to HOME / "OneDrive" / ..., and a user can
    move any of them to another drive. The old folder is then empty or stale,
    so Mike would look in the wrong place and say "nothing here". Windows'
    own answer is SHGetKnownFolderPath.
    """
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        import uuid
        from ctypes import wintypes

        class _GUID(ctypes.Structure):
            _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                        ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]

        u = uuid.UUID(guid)
        folder_id = _GUID(u.fields[0], u.fields[1], u.fields[2],
                          (ctypes.c_ubyte * 8)(*u.bytes[8:]))
        found = ctypes.c_wchar_p()
        if ctypes.windll.shell32.SHGetKnownFolderPath(
                ctypes.byref(folder_id), 0, None, ctypes.byref(found)) != 0:
            return None
        try:
            return Path(found.value) if found.value else None
        finally:
            ctypes.windll.ole32.CoTaskMemFree(found)
    except Exception:
        return None


def _user_folder(name: str, guid: str) -> Path:
    return _known_folder(guid) or HOME / name


DESKTOP = _user_folder("Desktop", "B4BFCC3A-DB2C-424C-B029-7FE99A87C641")

DOWNLOADS = _user_folder("Downloads", "374DE290-123F-4565-9164-39C4925E467B")

DOCUMENTS = _user_folder("Documents", "FDD39AD0-238F-46AF-ADB4-6C85480369C7")

PICTURES = _user_folder("Pictures", "33E28130-4E1E-4676-835A-98395C3BC3BB")

# Windows calls it Videos; the key stays "movies" for what the model already says.
MOVIES = _user_folder("Movies", "18989B1D-99B5-455B-841C-AB7C74E4DDFC")

MUSIC = _user_folder("Music", "4BD8D571-6D19-48D3-BE97-422220080E43")


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