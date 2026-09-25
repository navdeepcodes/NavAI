"""The signed-in session, kept on disk so Mike stays signed in across launches.

The session holds a refresh token — enough to act as the person until they
sign out — so on Windows it's encrypted with DPAPI (CryptProtectData, the
per-user key Windows keeps for exactly this): it can only be read back by the
same Windows user on the same computer, and a copied file is useless. On
other systems it's written readable by the owner only.

Alongside it, a small cache of the profile (name, email, photo) so Mike shows
who's signed in immediately and offline, before the network answers.
"""
from __future__ import annotations

import json
import os
import platform
from pathlib import Path

from logs.logger import logger

_DPAPI = b"MIKE-DPAPI1\n"
_PLAIN = b"MIKE-PLAIN1\n"


def folder() -> Path:
    from hostplatform import storage
    path = storage.data_dir() / "account"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _session_file() -> Path:
    return folder() / "session.bin"


def _profile_file() -> Path:
    return folder() / "profile.json"


def avatar_file() -> Path:
    return folder() / "avatar.png"


# ── DPAPI (Windows) ──────────────────────────────────────────────────────

def _dpapi(data: bytes, protect: bool) -> bytes:
    import ctypes
    from ctypes import wintypes

    class _Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    buf = ctypes.create_string_buffer(data, len(data))
    blob_in = _Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    blob_out = _Blob()
    CRYPTPROTECT_UI_FORBIDDEN = 0x01
    fn = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    args = ((ctypes.byref(blob_in), "Mike account", None, None, None,
             CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(blob_out)) if protect else
            (ctypes.byref(blob_in), None, None, None, None,
             CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(blob_out)))
    if not fn(*args):
        raise OSError(ctypes.GetLastError(), "DPAPI failed")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        kernel32.LocalFree(blob_out.pbData)


def _encode(raw: bytes) -> bytes:
    if platform.system() == "Windows":
        return _DPAPI + _dpapi(raw, protect=True)
    return _PLAIN + raw


def _decode(blob: bytes) -> bytes:
    if blob.startswith(_DPAPI):
        return _dpapi(blob[len(_DPAPI):], protect=False)
    if blob.startswith(_PLAIN):
        return blob[len(_PLAIN):]
    raise ValueError("unrecognised session file")


def _write_private(path: Path, data: bytes) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(data)
    os.replace(tmp, path)


# ── session ──────────────────────────────────────────────────────────────

def save(session: dict) -> None:
    _write_private(_session_file(), _encode(json.dumps(session).encode("utf-8")))


def load() -> dict | None:
    path = _session_file()
    if not path.exists():
        return None
    try:
        data = json.loads(_decode(path.read_bytes()).decode("utf-8"))
        return data if data.get("refresh_token") else None
    except Exception:
        # Unreadable (another Windows user, a copied file, corruption): the
        # only safe thing is to forget it and ask the person to sign in.
        logger.warning("The saved sign-in couldn't be read; signing out.", exc_info=True)
        clear()
        return None


# ── profile cache ────────────────────────────────────────────────────────

def save_profile(profile: dict) -> None:
    _write_private(_profile_file(), json.dumps(profile).encode("utf-8"))


def load_profile() -> dict:
    try:
        return json.loads(_profile_file().read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_avatar(data: bytes | None) -> None:
    if data:
        _write_private(avatar_file(), data)
    else:
        avatar_file().unlink(missing_ok=True)


def clear() -> None:
    """Forget the session and everything cached about the account."""
    for path in (_session_file(), _profile_file(), avatar_file()):
        try:
            path.unlink(missing_ok=True)
        except OSError:
            logger.warning("Could not remove %s", path.name, exc_info=True)
