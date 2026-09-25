"""Writes docs/legal/THIRD_PARTY_NOTICES.md — the open-source licences Mike ships.

    python packaging/generate_notices.py

Run by build_windows.py before every build, from the build's own environment,
so the versions and licences listed are the ones actually bundled. Packages
come from requirements.txt; each one's licence is read from its installed
metadata, falling back to a short table of known licences for packages that
don't declare one clearly (or that aren't installed on the machine generating
the file, e.g. Windows-only dependencies when run elsewhere).
"""
from __future__ import annotations

import os
import re
from importlib import metadata

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(REPO, "docs", "legal", "THIRD_PARTY_NOTICES.md")

#: Licences for packages whose metadata is missing, vague, or not installed here.
KNOWN = {
    "PySide6": "LGPL-3.0-only", "PySide6_Addons": "LGPL-3.0-only",
    "PySide6_Essentials": "LGPL-3.0-only", "shiboken6": "LGPL-3.0-only",
    "comtypes": "MIT", "pywin32": "PSF-2.0", "faster-whisper": "MIT",
    "ctranslate2": "MIT", "onnxruntime": "MIT", "av": "BSD-3-Clause",
    "tokenizers": "Apache-2.0", "huggingface_hub": "Apache-2.0",
    "hf-xet": "Apache-2.0", "PyYAML": "MIT", "filelock": "Unlicense",
    "fsspec": "BSD-3-Clause", "click": "BSD-3-Clause", "flatbuffers": "Apache-2.0",
    "numpy": "BSD-3-Clause", "Pygments": "BSD-2-Clause", "markdown-it-py": "MIT",
    "mdurl": "MIT", "pypdf": "BSD-3-Clause", "python-docx": "MIT",
    "python-pptx": "MIT", "openpyxl": "MIT", "et_xmlfile": "MIT",
    "lxml": "BSD-3-Clause", "pillow": "MIT-CMU", "sounddevice": "MIT",
    "soundfile": "BSD-3-Clause", "requests": "Apache-2.0", "urllib3": "MIT",
    "certifi": "MPL-2.0", "idna": "BSD-3-Clause", "charset-normalizer": "MIT",
    "ollama": "MIT", "httpx": "BSD-3-Clause", "httpcore": "BSD-3-Clause",
    "h11": "MIT", "anyio": "MIT", "sniffio": "MIT or Apache-2.0",
    "pydantic": "MIT", "pydantic_core": "MIT", "annotated-types": "MIT",
    "typing_extensions": "PSF-2.0", "typing-inspection": "MIT",
    "python-dotenv": "BSD-3-Clause", "tenacity": "Apache-2.0", "tqdm": "MPL-2.0 AND MIT",
    "google-api-python-client": "Apache-2.0", "google-auth": "Apache-2.0",
    "google-auth-oauthlib": "Apache-2.0", "google-auth-httplib2": "Apache-2.0",
    "google-api-core": "Apache-2.0", "googleapis-common-protos": "Apache-2.0",
    "google-genai": "Apache-2.0", "proto-plus": "Apache-2.0", "protobuf": "BSD-3-Clause",
    "httplib2": "MIT", "oauthlib": "BSD-3-Clause", "requests-oauthlib": "ISC",
    "pyasn1": "BSD-2-Clause", "pyasn1_modules": "BSD-2-Clause", "pyparsing": "MIT",
    "uritemplate": "BSD-3-Clause OR Apache-2.0", "cryptography": "Apache-2.0 OR BSD-3-Clause",
    "cffi": "MIT", "pycparser": "BSD-3-Clause", "jiter": "MIT", "distro": "Apache-2.0",
    "websockets": "BSD-3-Clause", "XlsxWriter": "BSD-2-Clause", "packaging": "Apache-2.0 OR BSD-2-Clause",
}

ASSETS = """## Bundled assets

**Source Serif 4** — Mike's typeface. © 2014–2021 Adobe Systems Incorporated,
with Reserved Font Name "Source". Licensed under the SIL Open Font License 1.1
(the full licence ships as `ui/fonts/OFL.txt`).

**Hershey Script** — the pen strokes Mike writes with. The Hershey fonts were
originally created by Dr. A. V. Hershey while working at the U. S. National
Bureau of Standards. Public domain; extracted via the Hershey-Fonts package
(MIT). See `ui/fonts/HERSHEY.txt`.

**Qt and PySide6** — Mike's interface toolkit, © The Qt Company, used under the
GNU Lesser General Public License v3. The Qt libraries ship as separate files in
Mike's application folder and can be replaced with your own build. Source code
is available from https://code.qt.io and https://download.qt.io/official_releases/QtForPython/.

**Piper** — Mike's neural voice runtime (MIT), with voice models from the Piper
voices collection. Each voice model's own licence is in the model card that
ships beside it in the `piper/voices` folder.

**Language and speech models** — Mike's language model is downloaded and run by
Ollama (MIT, installed separately) and is subject to its own licence, which
`ollama show <model> --license` displays. Speech recognition uses Whisper models
(MIT) via faster-whisper.
"""


def _requirements() -> list[str]:
    names = []
    with open(os.path.join(REPO, "requirements.txt"), encoding="utf-8") as fh:
        for line in fh:
            line = line.split("#")[0].strip()
            if not line:
                continue
            name = re.split(r"[=<>;\s\[]", line, maxsplit=1)[0].strip()
            if name:
                names.append(name)
    return sorted(set(names), key=str.lower)


def _licence(dist) -> str:
    md = dist.metadata
    expr = md.get("License-Expression")
    if expr:
        return expr
    classifiers = [c.split("::")[-1].strip() for c in md.get_all("Classifier") or []
                   if c.startswith("License ::")]
    lic = (md.get("License") or "").strip()
    if lic and len(lic) < 60 and "\n" not in lic:
        return lic
    return ", ".join(classifiers) if classifiers else ""


def build() -> str:
    rows = []
    for name in _requirements():
        version, licence, home = "", "", ""
        try:
            dist = metadata.distribution(name)
            version = dist.version
            licence = _licence(dist)
            home = dist.metadata.get("Home-page") or ""
            if not home:
                for url in dist.metadata.get_all("Project-URL") or []:
                    home = url.split(",", 1)[-1].strip()
                    break
        except metadata.PackageNotFoundError:
            pass
        if not licence or licence.upper() in ("UNKNOWN", "OTHER/PROPRIETARY LICENSE"):
            licence = KNOWN.get(name, licence or "See the project's licence")
        rows.append(f"| {name} | {version or '—'} | {licence} | {home} |")
    table = "\n".join(["| Package | Version | Licence | Project |",
                       "|---|---|---|---|", *rows])
    return (
        "# Open-source licences\n\n"
        "Mike is built on open-source software. We're grateful to everyone who "
        "made it. Each component is used under its own licence, listed below; "
        "nothing in Mike's Terms of Use limits your rights under these licences.\n\n"
        + ASSETS + "\n## Python packages\n\n" + table + "\n"
    )


def main() -> None:
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(build())
    print("wrote", os.path.relpath(OUT, REPO))


if __name__ == "__main__":
    main()
