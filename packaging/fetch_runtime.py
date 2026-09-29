"""Fetch the Piper voice runtime into runtime/piper, for a build.

    python packaging/fetch_runtime.py

runtime/ is git-ignored (it's ~150 MB of binaries and voice models), so a
fresh checkout -- GitHub's Windows build machine, or any new laptop -- didn't
have it, and packaging/mike.spec bundles it: the build either failed or, worse,
would have shipped a Mike with no neural voice. This downloads exactly the
files the released Mike ships, each checked against a pinned SHA-256 (the
same files that were set up by hand on the development laptop, verified
byte-for-byte), and does nothing when they are already in place.
"""
from __future__ import annotations

import hashlib
import io
import sys
import urllib.request
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PIPER_DIR = REPO_ROOT / "runtime" / "piper"

PIPER_ZIP = ("https://github.com/rhasspy/piper/releases/download/2023.11.14-2/"
             "piper_windows_amd64.zip",
             "f3c58906402b24f3a96d92145f58acba6d86c9b5db896d207f78dc80811efcea")
_VOICES = "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US"
VOICES = {
    "en_US-amy-medium.onnx": (f"{_VOICES}/amy/medium/en_US-amy-medium.onnx",
        "b3a6e47b57b8c7fbe6a0ce2518161a50f59a9cdd8a50835c02cb02bdd6206c18"),
    "en_US-amy-medium.onnx.json": (f"{_VOICES}/amy/medium/en_US-amy-medium.onnx.json",
        "95a23eb4d42909d38df73bb9ac7f45f597dbfcde2d1bf9526fdeaf5466977d77"),
    "en_US-lessac-medium.onnx": (f"{_VOICES}/lessac/medium/en_US-lessac-medium.onnx",
        "5efe09e69902187827af646e1a6e9d269dee769f9877d17b16b1b46eeaaf019f"),
    "en_US-lessac-medium.onnx.json": (f"{_VOICES}/lessac/medium/en_US-lessac-medium.onnx.json",
        "efe19c417bed055f2d69908248c6ba650fa135bc868b0e6abb3da181dab690a0"),
}


def _download(url: str, sha256: str) -> bytes:
    print(f"   {url.rsplit('/', 1)[-1]}...")
    with urllib.request.urlopen(url, timeout=120) as response:
        data = response.read()
    got = hashlib.sha256(data).hexdigest()
    if got != sha256:
        sys.exit(f"{url} doesn't match its pinned SHA-256 ({got}); not using it.")
    return data


def _has(path: Path, sha256: str) -> bool:
    return path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == sha256


def main() -> None:
    if not (PIPER_DIR / "piper.exe").is_file():
        print("-> Fetching the Piper runtime...")
        url, sha = PIPER_ZIP
        with zipfile.ZipFile(io.BytesIO(_download(url, sha))) as zf:
            for member in zf.infolist():
                if not member.filename.startswith("piper/") or member.is_dir():
                    continue
                target = PIPER_DIR / member.filename.split("/", 1)[1]
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(zf.read(member))
    voices = PIPER_DIR / "voices"
    voices.mkdir(parents=True, exist_ok=True)
    for name, (url, sha) in VOICES.items():
        if not _has(voices / name, sha):
            print(f"-> Fetching the {name} voice...")
            (voices / name).write_bytes(_download(url, sha))
    print("-> Piper runtime ready.")


if __name__ == "__main__":
    main()
