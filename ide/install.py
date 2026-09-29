"""Get Mike's VS Code extension onto the machine, without asking the user
to know what a .vsix is.

The editor integration is two halves: ide/bridge.py inside Mike, and a small
extension inside VS Code. Only one half was ever shipped. On a clean machine
the bridge starts, listens on 8787, and nothing connects -- not because
anything is broken, but because the other half is a file in the repo that a
student downloading a zip has never seen. Verified on this machine: VS Code
installed, `code --list-extensions` showing no mike-bridge, and every editor
command returning "No editor is connected to Mike right now."

So Mike installs it himself, once, in the background. `code
--install-extension` is VS Code's own supported path for this and needs no
elevation.

Deliberately best-effort and quiet. A machine with no VS Code is the common
case, not an error, and nothing else about Mike depends on this succeeding.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from config import preferences
from logs.logger import logger

EXTENSION_ID = "mike.mike-bridge"
#: The bundled extension. When VS Code has an older one, it's updated: 0.2
#: brought "Mike: Ask about this" and edits made in the editor itself; 0.3
#: the terminal (what ran and what it printed, and Mike's servers running
#: there) and VS Code's own checks on the files Mike writes.
EXTENSION_VERSION = "0.3.1"
VSIX_NAME = f"mike-bridge-{EXTENSION_VERSION}.vsix"
_PREF_KEY = "vscode_extension_offered"

# Where VS Code's CLI usually is when `code` is not on PATH. A student who
# installed VS Code normally often does not have it on PATH, and that alone
# would be enough to make the integration silently never happen.
_CLI_CANDIDATES = (
    r"%LOCALAPPDATA%\Programs\Microsoft VS Code\bin\code.cmd",
    r"%PROGRAMFILES%\Microsoft VS Code\bin\code.cmd",
    r"%PROGRAMFILES(X86)%\Microsoft VS Code\bin\code.cmd",
    r"%USERPROFILE%\Downloads\Microsoft VS Code\bin\code.cmd",
)

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def find_vscode_cli() -> str | None:
    """VS Code's command line tool, or None if this machine hasn't got it."""
    found = shutil.which("code")
    if found:
        return found
    for raw in _CLI_CANDIDATES:
        path = Path(os.path.expandvars(raw))
        if path.is_file():
            return str(path)
    return None


def bundled_vsix() -> Path | None:
    """The extension file, whether Mike is frozen or running from source."""
    roots = [
        Path(getattr(sys, "_MEIPASS", "")) / "vscode-extension",
        Path(sys.executable).parent / "vscode-extension",
        Path(__file__).resolve().parent.parent / "vscode-extension",
    ]
    for root in roots:
        candidate = root / VSIX_NAME
        if candidate.is_file():
            return candidate
    return None


def installed_version(cli: str) -> str | None:
    """The version of Mike's extension VS Code has, or None if it hasn't."""
    try:
        out = subprocess.run(
            [cli, "--list-extensions", "--show-versions"], capture_output=True, text=True,
            timeout=60, creationflags=_NO_WINDOW,
        )
    except Exception:
        logger.debug("Could not list VS Code extensions.", exc_info=True)
        return None
    for line in (out.stdout or "").splitlines():
        name, _, version = line.strip().partition("@")
        if name.lower() == EXTENSION_ID:
            return version or "0"
    return None


def already_installed(cli: str) -> bool:
    return installed_version(cli) is not None


def _older(have: str, want: str) -> bool:
    def parts(v: str) -> tuple[int, ...]:
        return tuple(int(p) if p.isdigit() else 0 for p in v.split("."))
    return parts(have) < parts(want)


def ensure_installed(force: bool = False) -> tuple[bool, str]:
    """Install the bridge extension if VS Code is here and it isn't, or bring
    an older copy up to date.

    Returns (changed, human_readable_reason). A first install happens once per
    machine unless forced -- a user who uninstalls it deliberately should not
    have Mike quietly put it back on every launch. An installed copy that's
    older than Mike's is updated: it's theirs to keep, at the version that
    works with this Mike.
    """
    cli = find_vscode_cli()
    if not cli:
        return False, "VS Code is not installed on this machine"

    have = installed_version(cli)
    if have is not None and not _older(have, EXTENSION_VERSION):
        preferences.set_value(_PREF_KEY, True)
        return False, "the extension is already installed and up to date"
    if have is None and not force and preferences.get(_PREF_KEY, False):
        return False, "already offered once"

    vsix = bundled_vsix()
    if vsix is None:
        return False, "the extension file was not bundled with this build"

    try:
        result = subprocess.run(
            [cli, "--install-extension", str(vsix), "--force"],
            capture_output=True, text=True, timeout=180,
            creationflags=_NO_WINDOW,
        )
    except Exception as exc:
        logger.debug("VS Code extension install failed.", exc_info=True)
        return False, f"the install command could not run ({exc})"

    preferences.set_value(_PREF_KEY, True)
    if result.returncode == 0:
        logger.info("%s Mike's VS Code extension (%s).",
                    "Updated" if have else "Installed", EXTENSION_VERSION)
        # VS Code only activates a newly installed extension on its next
        # start, so this is worth saying rather than leaving the user to
        # wonder why the editor still isn't connected.
        if have:
            return True, "updated -- reload VS Code windows for the new editor features"
        return True, "installed -- restart VS Code for Mike to see your editor"

    logger.debug("VS Code install returned %s: %s", result.returncode, result.stderr[:200])
    return False, "VS Code refused the install"
