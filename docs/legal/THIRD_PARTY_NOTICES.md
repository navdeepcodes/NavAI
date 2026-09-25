# Open-source licences

Mike is built on open-source software. We're grateful to everyone who made it. Each component is used under its own licence, listed below; nothing in Mike's Terms of Use limits your rights under these licences.

## Bundled assets

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

## Python packages

| Package | Version | Licence | Project |
|---|---|---|---|
| annotated-types | 0.7.0 | MIT License | https://github.com/annotated-types/annotated-types |
| anyio | 4.14.1 | MIT | https://anyio.readthedocs.io/en/latest/ |
| av | — | BSD-3-Clause |  |
| certifi | 2026.6.17 | MPL-2.0 | https://github.com/certifi/python-certifi |
| cffi | 2.0.0 | MIT | https://cffi.readthedocs.io/ |
| charset-normalizer | 3.4.7 | MIT | https://github.com/jawah/charset_normalizer/blob/master/CHANGELOG.md |
| click | — | BSD-3-Clause |  |
| comtypes | — | MIT |  |
| cryptography | 49.0.0 | Apache-2.0 OR BSD-3-Clause | https://cryptography.io/en/latest/changelog/ |
| ctranslate2 | — | MIT |  |
| distro | 1.9.0 | Apache License, Version 2.0 | https://github.com/python-distro/distro |
| et_xmlfile | 2.0.0 | MIT | https://foss.heptapod.net/openpyxl/et_xmlfile |
| faster-whisper | — | MIT |  |
| filelock | — | Unlicense |  |
| flatbuffers | — | Apache-2.0 |  |
| fsspec | — | BSD-3-Clause |  |
| google-api-core | 2.31.0 | Apache 2.0 | https://github.com/googleapis/google-cloud-python/tree/main/packages/google-api-core |
| google-api-python-client | 2.198.0 | Apache 2.0 | https://github.com/googleapis/google-api-python-client/ |
| google-auth | 2.55.1 | Apache 2.0 | https://github.com/googleapis/google-cloud-python/tree/main/packages/google-auth |
| google-auth-httplib2 | 0.4.0 | Apache 2.0 | https://github.com/googleapis/google-cloud-python/packages/google-auth-httplib2 |
| google-auth-oauthlib | 1.4.0 | Apache 2.0 | https://github.com/googleapis/google-cloud-python/tree/main/packages/google-auth-oauthlib |
| google-genai | 2.10.0 | Apache-2.0 | https://github.com/googleapis/python-genai |
| googleapis-common-protos | 1.75.0 | Apache 2.0 | https://github.com/googleapis/google-cloud-python/tree/main/packages/googleapis-common-protos |
| h11 | 0.16.0 | MIT | https://github.com/python-hyper/h11 |
| hf-xet | — | Apache-2.0 |  |
| httpcore | 1.0.9 | BSD-3-Clause | https://www.encode.io/httpcore |
| httplib2 | 0.32.0 | MIT | https://github.com/httplib2/httplib2 |
| httpx | 0.28.1 | BSD-3-Clause | https://github.com/encode/httpx/blob/master/CHANGELOG.md |
| huggingface_hub | — | Apache-2.0 |  |
| idna | 3.18 | BSD-3-Clause | https://github.com/kjd/idna/blob/master/HISTORY.md |
| jiter | 0.16.0 | MIT | https://github.com/pydantic/jiter/ |
| lxml | 6.1.3 | BSD-3-Clause | https://lxml.de/ |
| markdown-it-py | 4.2.0 | MIT License | https://markdown-it-py.readthedocs.io |
| mdurl | 0.1.2 | MIT License | https://github.com/executablebooks/mdurl |
| numpy | 2.5.0 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 | https://numpy.org |
| oauthlib | 3.3.1 | BSD-3-Clause | https://github.com/oauthlib/oauthlib |
| ollama | 0.6.2 | MIT | https://ollama.com |
| onnxruntime | — | MIT |  |
| openpyxl | 3.1.5 | MIT | https://openpyxl.readthedocs.io |
| packaging | 26.2 | Apache-2.0 OR BSD-2-Clause | https://packaging.pypa.io/ |
| pillow | 12.3.0 | MIT-CMU | https://pillow.readthedocs.io/en/stable/releasenotes/index.html |
| proto-plus | 1.28.0 | Apache 2.0 | https://googleapis.dev/python/proto-plus/latest/ |
| protobuf | 7.35.1 | 3-Clause BSD License | https://developers.google.com/protocol-buffers/ |
| pyasn1 | 0.6.3 | BSD-2-Clause | https://github.com/pyasn1/pyasn1 |
| pyasn1_modules | 0.4.2 | BSD | https://github.com/pyasn1/pyasn1-modules |
| pycparser | 3.0 | BSD-3-Clause | https://github.com/eliben/pycparser |
| pydantic | 2.13.4 | MIT | https://github.com/pydantic/pydantic |
| pydantic_core | 2.46.4 | MIT | https://github.com/pydantic/pydantic |
| Pygments | 2.21.0 | BSD-2-Clause | https://pygments.org |
| pyobjc-core | — | See the project's licence |  |
| pyobjc-framework-AVFoundation | — | See the project's licence |  |
| pyobjc-framework-Cocoa | — | See the project's licence |  |
| pyobjc-framework-Speech | — | See the project's licence |  |
| pyparsing | 3.3.2 | MIT | https://pyparsing-docs.readthedocs.io/en/latest/ |
| pypdf | 6.19.0 | BSD-3-Clause | https://github.com/py-pdf/pypdf/issues |
| PySide6 | 6.11.1 | LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only | https://pyside.org |
| PySide6_Addons | 6.11.1 | LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only | https://pyside.org |
| PySide6_Essentials | 6.11.1 | LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only | https://pyside.org |
| python-docx | 1.2.0 | MIT | https://github.com/python-openxml/python-docx/blob/master/HISTORY.rst |
| python-dotenv | 1.2.2 | BSD-3-Clause | https://github.com/theskumar/python-dotenv |
| python-pptx | 1.0.2 | MIT | https://github.com/scanny/python-pptx/blob/master/HISTORY.rst |
| pywin32 | — | PSF-2.0 |  |
| PyYAML | — | MIT |  |
| requests | 2.34.2 | Apache-2.0 | https://requests.readthedocs.io |
| requests-oauthlib | 2.0.0 | ISC | https://github.com/requests/requests-oauthlib |
| shiboken6 | 6.11.1 | LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only | https://pyside.org |
| sniffio | 1.3.1 | MIT OR Apache-2.0 | https://github.com/python-trio/sniffio |
| sounddevice | 0.5.5 | MIT | https://python-sounddevice.readthedocs.io/ |
| soundfile | 0.14.0 | BSD 3-Clause License | https://github.com/bastibe/python-soundfile |
| tenacity | 9.1.4 | Apache 2.0 | https://github.com/jd/tenacity |
| tokenizers | — | Apache-2.0 |  |
| tqdm | 4.68.3 | MPL-2.0 AND MIT | https://tqdm.github.io |
| typing-inspection | 0.4.2 | MIT | https://github.com/pydantic/typing-inspection |
| typing_extensions | 4.15.0 | PSF-2.0 | https://github.com/python/typing_extensions/issues |
| uritemplate | 4.2.0 | BSD 3-Clause OR Apache-2.0 | https://uritemplate.readthedocs.org |
| urllib3 | 2.7.0 | MIT | https://github.com/urllib3/urllib3/blob/main/CHANGES.rst |
| websockets | 16.0 | BSD-3-Clause | https://github.com/python-websockets/websockets |
| XlsxWriter | 3.2.9 | BSD-2-Clause | https://github.com/jmcnamara/XlsxWriter |
