"""Document reader — extracts text from PDF, DOCX, PPTX, and plain text files.

All processing is local. No cloud services.
"""
from __future__ import annotations

import csv
import io
import json
from pathlib import Path

from tools.filesystem.path_utils import resolve_path

MAX_TEXT_CHARS = 12_000
MAX_FILE_BYTES = 50_000_000


def read_document(path: str) -> str:
    file = resolve_path(path)

    if not file.exists():
        raise FileNotFoundError(f"File not found: {file}")

    size = file.stat().st_size
    if size > MAX_FILE_BYTES:
        return f"This file is too large ({size / 1_000_000:.1f} MB). Maximum supported size is {MAX_FILE_BYTES / 1_000_000:.0f} MB."

    suffix = file.suffix.lower()

    if suffix == ".pdf":
        text = _read_pdf(file)
    elif suffix == ".docx":
        text = _read_docx(file)
    elif suffix == ".pptx":
        text = _read_pptx(file)
    elif suffix == ".csv":
        text = _read_csv(file)
    elif suffix == ".json":
        text = _read_json(file)
    elif suffix in (".txt", ".md", ".py", ".js", ".ts", ".jsx", ".tsx",
                     ".html", ".css", ".yaml", ".yml", ".toml", ".ini",
                     ".cfg", ".sh", ".bash", ".zsh", ".rb", ".go", ".rs",
                     ".java", ".kt", ".swift", ".c", ".cpp", ".h", ".hpp",
                     ".sql", ".xml", ".env", ".gitignore", ".dockerfile",
                     ".makefile", ".r", ".m", ".lua", ".pl", ".php",
                     ".scala", ".ex", ".exs", ".hs", ".clj", ".dart",
                     ".vue", ".svelte", ""):
        text = _read_text(file)
    else:
        text = _try_text(file)

    if not text or not text.strip():
        if suffix == ".pdf":
            return (
                "This PDF appears to be image-based. "
                "I can't reliably read scanned pages yet."
            )
        return f"Could not extract text from this {suffix} file."

    if len(text) > MAX_TEXT_CHARS:
        truncated = text[:MAX_TEXT_CHARS]
        return (
            f"{truncated}\n\n"
            f"--- Truncated: showing first {MAX_TEXT_CHARS:,} of {len(text):,} characters. "
            f"The full document is {len(text):,} characters long. ---"
        )

    return text


def _read_pdf(file: Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(file))
    pages = []
    for i, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        if text.strip():
            pages.append(f"[Page {i + 1}]\n{text.strip()}")

    return "\n\n".join(pages)


def _read_docx(file: Path) -> str:
    from docx import Document

    doc = Document(str(file))
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    return "\n\n".join(paragraphs)


def _read_pptx(file: Path) -> str:
    from pptx import Presentation

    prs = Presentation(str(file))
    slides = []
    for i, slide in enumerate(prs.slides):
        texts = []
        for shape in slide.shapes:
            if shape.has_text_frame:
                for para in shape.text_frame.paragraphs:
                    if para.text.strip():
                        texts.append(para.text.strip())
        if texts:
            slides.append(f"[Slide {i + 1}]\n" + "\n".join(texts))

    return "\n\n".join(slides)


def _read_csv(file: Path) -> str:
    text = file.read_text(encoding="utf-8", errors="replace")
    reader = csv.reader(io.StringIO(text))
    rows = []
    for i, row in enumerate(reader):
        if i >= 100:
            rows.append(f"... ({i} rows shown of more)")
            break
        rows.append(" | ".join(row))
    return "\n".join(rows)


def _read_json(file: Path) -> str:
    text = file.read_text(encoding="utf-8", errors="replace")
    try:
        data = json.loads(text)
        formatted = json.dumps(data, indent=2, ensure_ascii=False)
        return formatted
    except json.JSONDecodeError:
        return text


def _read_text(file: Path) -> str:
    return file.read_text(encoding="utf-8", errors="replace")


def _try_text(file: Path) -> str:
    try:
        return file.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""
