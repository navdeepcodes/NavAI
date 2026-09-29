"""What Mike is told about a file the student attached.

Attached files used to arrive as their text (or, for a picture, a description
from the local picture model) under just the file's name. With no path, Mike
couldn't do anything WITH the file: merge two attached PDFs, make a PDF from
attached photos, convert or split one -- the tools need a path. And every
picture paid for a slow description, even a photo of notes that only needed
its words read.

Now each attachment comes as facts -- name, full path, what it is, how big --
plus a short preview of what's in it, so Mike knows what he has and reads the
rest (or does something with it) himself. A picture's text is read by OCR, which
is quick; only a picture with no text in it (a diagram, a photo of a thing) is
described by the picture model, as before.
"""
from __future__ import annotations

import os
from pathlib import Path

from logs.logger import logger

#: Preview budget for all the attachments in one message, in characters.
TOTAL_PREVIEW = 6000
PER_FILE_MIN = 800
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tif", ".tiff"}


def _size(path: Path) -> str:
    try:
        n = path.stat().st_size
    except OSError:
        return ""
    return f"{n / 1_000_000:.1f} MB" if n >= 1_000_000 else f"{max(1, round(n / 1000))} KB"


def _preview(text: str, limit: int) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[:limit].rstrip() + "\n…"


def describe(path: str, budget: int = PER_FILE_MIN, describe_image=None) -> str:
    """One attachment as text for Mike: its facts and a preview. `describe_image`
    (path -> text) is asked for a picture that has no readable text."""
    file = Path(path)
    name = file.name
    lines = [f"[The user attached a file: {name}]", f"path: {file}"]
    ext = file.suffix.lower()
    try:
        if not file.exists():
            return "\n".join(lines + ["(this file isn't there any more)", f"[end of {name}]"])
        if ext in IMAGE_EXTS:
            kind = "a picture"
            try:
                from PIL import Image
                with Image.open(file) as im:
                    kind = f"a picture, {im.size[0]}x{im.size[1]} pixels"
            except Exception:
                pass
            lines.append(f"kind: {kind}, {_size(file)}")
            from tools.documents import pages
            got = pages.read(str(file), max_chars=budget)
            words = got.get("text", "").split("\n", 1)[-1].strip() if got.get("status") == "success" else ""
            if words:
                lines += ["The text in it, read by OCR (it can misread numbers or handwriting):", _preview(words, budget)]
            elif describe_image is not None:
                lines += ["No text in it; here is what it shows:", _preview(str(describe_image(str(file)) or ""), budget)]
            else:
                lines.append("(no text in it, and nothing here can describe what it shows)")
        else:
            from tools.documents import pages
            info = pages.info(str(file))
            unit = info["unit"]
            facts = f"{info['kind'].upper() if info['kind'] != 'text' else 'text file'}, {info['count']} {unit}{'s' if info['count'] != 1 else ''}, {_size(file)}"
            if info.get("title"):
                facts += f', titled "{info["title"]}"'
            if info.get("scanned"):
                facts += ", scanned (pictures of text)"
            lines.append(f"kind: {facts}")
            got = pages.read(str(file), max_chars=budget)
            if got.get("status") == "success" and got.get("text"):
                lines += [f"The start of it ({unit} {got['shown']}):", _preview(got["text"], budget)]
                if got.get("next"):
                    lines.append(f"[Read the rest with read_document, pages {got['next']}; the file is at the path above for other tools.]")
            elif got.get("error"):
                lines.append(f"(couldn't read its text: {got['error']})")
    except Exception as exc:
        logger.debug("Couldn't describe the attachment %s", path, exc_info=True)
        lines.append(f"(couldn't read this file: {exc})")
        lines.append(f"kind: {ext or 'unknown'}, {_size(file)}")
    lines.append(f"[end of {name}]")
    return "\n".join(lines)


def describe_all(paths: list[str], describe_image=None, on_each=None) -> str:
    """All the attachments of one message, sharing the preview budget."""
    per = max(PER_FILE_MIN, TOTAL_PREVIEW // max(1, len(paths)))
    blocks = []
    for path in paths:
        if on_each:
            on_each(os.path.basename(path), True)
        blocks.append(describe(path, per, describe_image))
        if on_each:
            on_each(os.path.basename(path), False)
    return "\n\n".join(blocks)
