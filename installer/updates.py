"""Newer versions of Mike: finding one, fetching it, and handing over to it.

Mike is shipped as a zip on GitHub releases. Without this, everyone who
installed a version kept it until they happened to revisit the website -- a
bug fixed for a new download stayed unfixed for every student already using
Mike.

  check()      asks GitHub for Mike's releases and returns the newest Windows
               build that is newer than this one (None if there isn't one).
  download()   fetches that zip into Mike's data folder, checks it against the
               SHA-256 GitHub publishes for it, and unpacks it.
  hand_over()  starts the new Mike.exe in update mode; it waits for this Mike
               to quit, swaps the install folder (installer/core.copy_tree,
               which keeps the old version if anything fails) and starts
               itself from the install location.

Only GitHub is contacted, and only with what any download sends: no account,
no identifiers, nothing about what Mike has been doing.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path
from urllib.request import Request, urlopen

#: The public repository Mike's releases are published to.
REPO = "navdeepcodes/NavAI"
#: Where the list of releases is read from. MIKE_UPDATE_FEED points it at a
#: stand-in for tests (and for trying an update before publishing one).
DEFAULT_FEED = f"https://api.github.com/repos/{REPO}/releases?per_page=15"
ASSET = re.compile(r"^Mike-windows-(\d+(?:\.\d+)*)\.zip$", re.IGNORECASE)
TIMEOUT = 20


def feed() -> str:
    return os.environ.get("MIKE_UPDATE_FEED", "").strip() or DEFAULT_FEED


@dataclass
class Update:
    version: str
    url: str
    size: int
    sha256: str          # "" when the release doesn't publish one
    notes: str
    page: str

    @property
    def headline(self) -> str:
        """The first real sentence of the release notes (not a heading), for a
        one-line mention."""
        for line in (self.notes or "").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            return line.lstrip("*- ").strip()[:140]
        return ""


def version_tuple(text: str) -> tuple[int, ...]:
    """"v1.10.2" -> (1, 10, 2); anything unreadable sorts lowest."""
    parts = re.findall(r"\d+", str(text or ""))
    return tuple(int(p) for p in parts[:4]) or (0,)


def current_version() -> str:
    from config.settings import VERSION
    return VERSION


def newest(releases: list[dict], than: str) -> Update | None:
    """The newest published Windows build in `releases` newer than `than`."""
    best: Update | None = None
    for rel in releases or []:
        if rel.get("draft") or rel.get("prerelease"):
            continue
        for asset in rel.get("assets") or []:
            match = ASSET.match(str(asset.get("name", "")))
            if not match:
                continue
            version = match.group(1)
            if version_tuple(version) <= version_tuple(than):
                continue
            if best is not None and version_tuple(version) <= version_tuple(best.version):
                continue
            digest = str(asset.get("digest") or "")
            best = Update(
                version=version,
                url=str(asset.get("browser_download_url", "")),
                size=int(asset.get("size") or 0),
                sha256=digest.split(":", 1)[1].lower() if digest.startswith("sha256:") else "",
                notes=str(rel.get("body") or ""),
                page=str(rel.get("html_url") or f"https://github.com/{REPO}/releases"),
            )
    return best


def _get(url: str, timeout: float = TIMEOUT):
    request = Request(url, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": f"Mike/{current_version()} (update check)",
    })
    return urlopen(request, timeout=timeout)


def check() -> Update | None:
    """The newest version of Mike for Windows, if it is newer than this one.
    Raises on a network or GitHub failure, so the caller can say so."""
    with _get(feed()) as response:
        releases = json.loads(response.read().decode("utf-8"))
    if isinstance(releases, dict):          # a single release (releases/latest)
        releases = [releases]
    return newest(releases, current_version())


def updates_dir() -> Path:
    from hostplatform import storage
    path = storage.data_dir() / "updates"
    path.mkdir(parents=True, exist_ok=True)
    return path


def download(update: Update, on_progress=None, cancel=None) -> Path:
    """Fetch, verify and unpack `update`; the path of its Mike.exe.

    `on_progress(done_bytes, total_bytes)` is called as it arrives; `cancel()`
    returning True stops it."""
    folder = updates_dir()
    for old in folder.iterdir():             # an earlier, unfinished attempt
        if old.is_dir():
            shutil.rmtree(old, ignore_errors=True)
        else:
            try:
                old.unlink()
            except OSError:
                pass

    part = folder / f"Mike-windows-{update.version}.zip.part"
    digest = hashlib.sha256()
    done = 0
    with _get(update.url, timeout=60) as response, open(part, "wb") as out:
        total = int(response.headers.get("Content-Length") or update.size or 0)
        while True:
            if cancel and cancel():
                raise InterruptedError("Update cancelled.")
            chunk = response.read(1 << 20)
            if not chunk:
                break
            out.write(chunk)
            digest.update(chunk)
            done += len(chunk)
            if on_progress:
                on_progress(done, total)
    if update.size and done != update.size:
        part.unlink(missing_ok=True)
        raise IOError(f"The download stopped early ({done} of {update.size} bytes).")
    if update.sha256 and digest.hexdigest() != update.sha256:
        part.unlink(missing_ok=True)
        raise IOError("The download doesn't match the file that was published, so it wasn't used.")

    archive = part.with_suffix("")           # drop ".part"
    part.rename(archive)
    unpacked = folder / update.version
    with zipfile.ZipFile(archive) as zf:
        root = unpacked.resolve()
        for member in zf.namelist():         # never write outside the folder
            if not (unpacked / member).resolve().is_relative_to(root):
                raise IOError("The update contains an unsafe path.")
        zf.extractall(unpacked)
    archive.unlink(missing_ok=True)
    exe = unpacked / "Mike" / "Mike.exe"
    if not exe.is_file():
        raise IOError("The update doesn't contain Mike.exe.")
    return exe


def hand_over(exe: Path) -> None:
    """Start the new version in update mode. It waits for this process to quit
    before it touches the install folder, so the caller quits right after."""
    flags = 0
    if sys.platform == "win32":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    subprocess.Popen(
        [str(exe), "--update-from", str(os.getpid())],
        cwd=str(exe.parent), close_fds=True, creationflags=flags,
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def clean_up() -> None:
    """Remove a finished (or abandoned) update's files, unless this very
    process is running from them."""
    try:
        folder = updates_dir()
        here = Path(sys.executable).resolve()
        if here.is_relative_to(folder.resolve()):
            return
        shutil.rmtree(folder, ignore_errors=True)
    except Exception:
        pass
