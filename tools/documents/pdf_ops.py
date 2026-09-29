"""Working on PDFs and converting between formats: what a student does before a deadline.

Merge lecture PDFs, pull out the pages that matter, split a scan, take out or
reorder or rotate pages, fill in a form, compress a big file for an upload
limit, turn photos of notes into one PDF, and convert between Word, PowerPoint,
PDF and text. Every result goes to a NEW file beside the original (numbered if
the name is taken): nothing here changes or replaces a file the student has.
Each output is opened again afterwards, and the answer reports what is really
in it.

Word and PowerPoint do the conversions of their own formats when they are
installed (the only faithful way: fonts, layouts and images come out as they
look on screen); without them, Word files are converted from their text and
the answer says the layout is simplified.
"""
from __future__ import annotations

import difflib
import re
from pathlib import Path

from logs.logger import logger
from tools.documents import pages as _pages
from tools.filesystem.path_utils import resolve_path

CONVERT_TIMEOUT = 150.0


class OpError(Exception):
    """Something the student should be told, in plain words."""


def _unique(path: Path) -> Path:
    if not path.exists():
        return path
    n = 2
    while True:
        candidate = path.with_name(f"{path.stem} ({n}){path.suffix}")
        if not candidate.exists():
            return candidate
        n += 1


def _converted(out: str | None, base: Path, ext: str) -> Path:
    """Where a converted copy goes: the name the student gave, else the same name
    with the new ending (essay.docx -> essay.pdf) when that's free, else numbered."""
    if out:
        return _target(out, base, "", ext)
    return _unique(base.with_suffix(ext))


def _target(out: str | None, base: Path, label: str, ext: str = ".pdf") -> Path:
    if out:
        target = resolve_path(out)
        if target.suffix.lower() != ext:
            target = target.with_suffix(ext)
        return _unique(target)
    return _unique(base.with_name(f"{base.stem} ({label}){ext}"))


def _open(path: str, must_be: str = ".pdf"):
    from pypdf import PdfReader
    file = resolve_path(path)
    if not file.exists():
        raise OpError(f"File not found: {file}")
    if file.suffix.lower() != must_be:
        raise OpError(f"{file.name} isn't a {must_be.lstrip('.').upper()} file.")
    try:
        reader = PdfReader(str(file))
        if reader.is_encrypted and not reader.decrypt(""):
            raise OpError(f"{file.name} is password-protected. Save an unlocked copy first.")
        len(reader.pages)
    except OpError:
        raise
    except Exception as exc:
        raise OpError(f"{file.name} isn't a PDF I can open ({exc}).")
    return file, reader


def _save(writer, target: Path) -> dict:
    """Write, then read back: the real page count and size."""
    from pypdf import PdfReader
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "wb") as handle:
        writer.write(handle)
    count = len(PdfReader(str(target)).pages)
    return {"path": str(target), "pages": count, "size_kb": round(target.stat().st_size / 1024)}


def _pick(reader, spec, file: Path) -> list[int]:
    try:
        wanted = _pages.parse_pages(spec, len(reader.pages))
    except ValueError as exc:
        raise OpError(str(exc))
    if not wanted:
        raise OpError("Say which pages, like 3, 3-7 or 1,4,9-11.")
    return wanted


# ── the operations ───────────────────────────────────────────

def merge(paths: list[str], out: str | None = None) -> dict:
    from pypdf import PdfWriter
    if not paths or len(paths) < 2:
        raise OpError("Merging needs at least two PDFs.")
    writer = PdfWriter()
    total = 0
    first = None
    for path in paths:
        file, reader = _open(path)
        first = first or file
        for page in reader.pages:
            writer.add_page(page)
        total += len(reader.pages)
        try:
            writer.add_outline_item(file.stem, total - len(reader.pages))     # a bookmark for each source
        except Exception:
            pass
    saved = _save(writer, _target(out, first, "merged"))
    saved["result"] = f"Merged {len(paths)} PDFs into {Path(saved['path']).name}: {saved['pages']} pages."
    return saved


def extract(path: str, pages, out: str | None = None) -> dict:
    from pypdf import PdfWriter
    file, reader = _open(path)
    wanted = _pick(reader, pages, file)
    writer = PdfWriter()
    for n in wanted:
        writer.add_page(reader.pages[n - 1])
    saved = _save(writer, _target(out, file, f"pages {_pages.ranges(wanted)}"))
    saved["result"] = f"Took pages {_pages.ranges(wanted)} out of {file.name} into {Path(saved['path']).name}."
    return saved


def delete_pages(path: str, pages, out: str | None = None) -> dict:
    from pypdf import PdfWriter
    file, reader = _open(path)
    gone = set(_pick(reader, pages, file))
    keep = [n for n in range(1, len(reader.pages) + 1) if n not in gone]
    if not keep:
        raise OpError("That would remove every page.")
    writer = PdfWriter()
    for n in keep:
        writer.add_page(reader.pages[n - 1])
    saved = _save(writer, _target(out, file, "edited"))
    saved["result"] = f"Removed pages {_pages.ranges(sorted(gone))}: {Path(saved['path']).name} has {saved['pages']} pages."
    return saved


def rotate(path: str, degrees: int = 90, pages=None, out: str | None = None) -> dict:
    from pypdf import PdfWriter
    file, reader = _open(path)
    try:
        degrees = int(degrees)
    except (TypeError, ValueError):
        raise OpError("Rotate by 90, 180 or 270 degrees.")
    if degrees % 90:
        raise OpError("Rotate by 90, 180 or 270 degrees.")
    chosen = set(_pick(reader, pages, file)) if pages else set(range(1, len(reader.pages) + 1))
    writer = PdfWriter()
    for n in range(1, len(reader.pages) + 1):
        page = reader.pages[n - 1]
        if n in chosen:
            page.rotate(degrees)
        writer.add_page(page)
    saved = _save(writer, _target(out, file, "rotated"))
    saved["result"] = f"Rotated {len(chosen)} page(s) by {degrees}° into {Path(saved['path']).name}."
    return saved


def reorder(path: str, order, out: str | None = None) -> dict:
    """The pages in a new order: "3,1,2" or "4-6,1-3". Pages not listed are left out."""
    from pypdf import PdfWriter
    file, reader = _open(path)
    sequence = _pages.parse_pages(order, len(reader.pages)) if order else []
    if not sequence:
        raise OpError("Give the new order, like 3,1,2 or 4-6,1-3.")
    writer = PdfWriter()
    for n in sequence:
        writer.add_page(reader.pages[n - 1])
    saved = _save(writer, _target(out, file, "reordered"))
    saved["result"] = f"Reordered into {Path(saved['path']).name}: {saved['pages']} pages."
    return saved


def split(path: str, every: int | None = None, ranges: str | None = None, out_dir: str | None = None) -> dict:
    """Split into several PDFs: every N pages, or by ranges like "1-3;4-9;10-"."""
    from pypdf import PdfWriter
    file, reader = _open(path)
    total = len(reader.pages)
    groups: list[list[int]] = []
    if ranges:
        for part in re.split(r"[;|]", str(ranges)):
            if part.strip():
                groups.append(_pick(reader, part.strip(), file))
    elif every:
        try:
            step = max(1, int(every))
        except (TypeError, ValueError):
            raise OpError("'every' must be a number of pages.")
        groups = [list(range(i, min(i + step, total + 1))) for i in range(1, total + 1, step)]
    else:
        raise OpError("Say how to split: every N pages, or ranges like 1-3;4-9.")
    folder = resolve_path(out_dir) if out_dir else file.parent
    made = []
    for i, group in enumerate(groups, start=1):
        writer = PdfWriter()
        for n in group:
            writer.add_page(reader.pages[n - 1])
        saved = _save(writer, _unique(folder / f"{file.stem} - part {i} (pages {_pages.ranges(group)}).pdf"))
        made.append({"path": saved["path"], "pages": saved["pages"]})
    return {"files": made, "count": len(made),
            "result": f"Split {file.name} into {len(made)} files in {folder}."}


def compress(path: str, out: str | None = None) -> dict:
    """A smaller copy: page streams recompressed, duplicate objects merged and,
    for pictures, re-encoded at a lower JPEG quality. Says how much it saved."""
    from pypdf import PdfWriter
    file, reader = _open(path)
    writer = PdfWriter(clone_from=reader)
    for page in writer.pages:
        page.compress_content_streams()
        try:
            for image in page.images:
                image.replace(image.image, quality=60)
        except Exception:
            logger.debug("Couldn't re-encode an image while compressing.", exc_info=True)
    try:
        writer.compress_identical_objects(remove_duplicates=True, remove_unreferenced=True)
    except TypeError:                     # an older pypdf
        writer.compress_identical_objects(remove_identicals=True, remove_orphans=True)
    saved = _save(writer, _target(out, file, "compressed"))
    before = round(file.stat().st_size / 1024)
    saved["before_kb"] = before
    saved["result"] = (f"{Path(saved['path']).name}: {saved['size_kb']:,} KB, from {before:,} KB "
                       f"({max(0, 100 - round(100 * saved['size_kb'] / max(1, before)))}% smaller)."
                       + ("" if saved["size_kb"] < before else " It couldn't be made smaller."))
    return saved


def form_fields(path: str) -> dict:
    file, reader = _open(path)
    fields = reader.get_fields() or {}
    listed = []
    for name, field in fields.items():
        kind = {"/Tx": "text", "/Btn": "checkbox or choice", "/Ch": "dropdown", "/Sig": "signature"}.get(
            str(field.get("/FT")), str(field.get("/FT") or "?"))
        entry = {"name": name, "type": kind, "value": str(field.get("/V") or "")}
        states = [str(s) for s in (field.get("/_States_") or []) if str(s) != "/Off"]
        if states:
            entry["options"] = states
        if field.get("/Opt"):
            entry["options"] = [str(o) for o in field["/Opt"]]
        listed.append(entry)
    return {"fields": listed, "count": len(listed),
            "result": (f"{file.name} has {len(listed)} fillable field(s)." if listed else
                       f"{file.name} has no fillable fields: it's a flat PDF (fill it by typing over it in a PDF reader).")}


def _set_field_directly(page, name: str, value) -> None:
    from pypdf.generic import NameObject, TextStringObject
    for annot in page.get("/Annots", []) or []:
        widget = annot.get_object()
        if str(widget.get("/T") or "") != name:
            continue
        if isinstance(value, str) and value.startswith("/"):        # a checkbox or radio state
            widget[NameObject("/V")] = NameObject(value)
            widget[NameObject("/AS")] = NameObject(value)
        else:
            widget[NameObject("/V")] = TextStringObject(str(value))


def fill_form(path: str, values: dict, out: str | None = None) -> dict:
    from pypdf import PdfWriter
    file, reader = _open(path)
    fields = reader.get_fields() or {}
    if not fields:
        raise OpError(f"{file.name} has no fillable fields.")
    if not isinstance(values, dict) or not values:
        raise OpError("Give the values to fill in, as field name -> value.")
    known = {str(k): v for k, v in fields.items()}
    to_set: dict = {}
    unknown = []
    for name, value in values.items():
        match = name if name in known else next((k for k in known if k.lower() == str(name).lower()), None)
        if match is None:
            close = difflib.get_close_matches(str(name), list(known), n=3)
            unknown.append(f"{name}" + (f" (did you mean {', '.join(close)}?)" if close else ""))
            continue
        field = known[match]
        if isinstance(value, bool):
            on = next((str(s) for s in (field.get("/_States_") or []) if str(s) != "/Off"), "/Yes")
            value = on if value else "/Off"
        to_set[match] = value
    if not to_set:
        raise OpError("None of those names are fields in this form. Fields: " + ", ".join(list(known)[:20]))
    writer = PdfWriter(clone_from=reader)
    for page in writer.pages:
        for name, value in to_set.items():
            try:
                writer.update_page_form_field_values(page, {name: value}, auto_regenerate=False)
            except Exception:
                # A field with no appearance data (some forms are built that
                # way): set its value directly rather than lose the whole fill.
                _set_field_directly(page, name, value)
    writer.set_need_appearances_writer(True)
    saved = _save(writer, _target(out, file, "filled"))
    back = _open(saved["path"])[1].get_fields() or {}
    wrong = [k for k, v in to_set.items() if str((back.get(k) or {}).get("/V") or "") not in (str(v), "")]
    saved["filled"] = len(to_set)
    if unknown:
        saved["not_found"] = unknown
    if wrong:
        saved["check"] = f"These didn't read back as set: {', '.join(wrong)}."
    saved["result"] = f"Filled {len(to_set)} field(s) into {Path(saved['path']).name}." + (
        f" Couldn't find: {'; '.join(unknown)}." if unknown else "")
    return saved


def from_images(paths: list[str], out: str | None = None) -> dict:
    """Photos or scans -> one PDF, a page each, in the order given."""
    from PIL import Image, ImageOps
    if not paths:
        raise OpError("Give the pictures to put in the PDF.")
    images = []
    first = None
    for p in paths:
        file = resolve_path(p)
        if not file.is_file():
            raise OpError(f"Picture not found: {file}")
        first = first or file
        try:
            with Image.open(file) as raw:
                image = ImageOps.exif_transpose(raw).convert("RGB")     # a phone photo's rotation applied
            images.append(image)
        except Exception as exc:
            raise OpError(f"{file.name} isn't a picture I can open ({exc}).")
    target = _target(out, first, "combined" if len(images) > 1 else "pdf")
    target.parent.mkdir(parents=True, exist_ok=True)
    images[0].save(str(target), "PDF", save_all=True, append_images=images[1:], resolution=150.0)
    back = _open(str(target))[1]
    return {"path": str(target), "pages": len(back.pages), "size_kb": round(target.stat().st_size / 1024),
            "result": f"Made {target.name} from {len(images)} picture(s): {len(back.pages)} page(s)."}


def info(path: str) -> dict:
    file, reader = _open(path)
    meta = reader.metadata or {}
    return {"path": str(file), "pages": len(reader.pages), "size_kb": round(file.stat().st_size / 1024),
            "title": str(getattr(meta, "title", "") or ""), "author": str(getattr(meta, "author", "") or ""),
            "form_fields": len(reader.get_fields() or {}),
            "result": f"{file.name}: {len(reader.pages)} pages."}


# ── conversions ──────────────────────────────────────────────

_WORD_SCRIPT = """
param([string]$Src, [string]$Dst)
$ErrorActionPreference = 'Stop'
$w = New-Object -ComObject Word.Application
try {
    $w.Visible = $false
    $w.DisplayAlerts = 0
    $d = $w.Documents.Open($Src, $false, $true)
    $d.ExportAsFixedFormat($Dst, 17)
    $d.Close($false)
} finally { $w.Quit() }
"""

_POWERPOINT_SCRIPT = """
param([string]$Src, [string]$Dst)
$ErrorActionPreference = 'Stop'
$p = New-Object -ComObject PowerPoint.Application
try {
    $deck = $p.Presentations.Open($Src, -1, 0, 0)
    $deck.SaveAs($Dst, 32)
    $deck.Close()
} finally { $p.Quit() }
"""


def _office_convert(app_name: str, source: Path, target: Path) -> None:
    """Have Word or PowerPoint save the file as a PDF -- in an instance of its
    own (never the student's open one), in a separate PowerShell process, so a
    COM hiccup can't reach Mike (driven in-process beside Qt it crashed the
    test run), and gone again afterwards."""
    import subprocess
    import tempfile

    from hostplatform.processes import NO_WINDOW
    name = app_name.split(".")[0]
    script = _WORD_SCRIPT if app_name == "Word.Application" else _POWERPOINT_SCRIPT
    with tempfile.TemporaryDirectory(prefix="mike-office-") as tmp:
        ps1 = Path(tmp) / "convert.ps1"
        ps1.write_text(script, encoding="utf-8-sig")
        try:
            proc = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(ps1),
                 "-Src", str(source), "-Dst", str(target)],
                capture_output=True, text=True, timeout=CONVERT_TIMEOUT, creationflags=NO_WINDOW,
                stdin=subprocess.DEVNULL)
        except subprocess.TimeoutExpired:
            raise OpError(f"{name} took too long to convert {source.name}.")
        except OSError as exc:
            raise OpError(f"Couldn't start {name} to convert {source.name} ({exc}).")
    if proc.returncode != 0 or not target.exists():
        detail = " ".join((proc.stderr or proc.stdout or "").split())[:160]
        raise OpError(f"{name} couldn't convert {source.name}" + (f": {detail}" if detail else "."))


def _office_available(app_name: str) -> bool:
    """Is Word or PowerPoint installed? Asked of the registry, so nothing is started."""
    try:
        import winreg
        winreg.CloseKey(winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, app_name + "\\CLSID"))
        return True
    except (ImportError, OSError):
        return False


def docx_to_markdown(file: Path) -> str:
    """A Word file's text as Markdown: headings, paragraphs, bullet lists, tables."""
    from docx import Document
    from docx.table import Table
    from docx.text.paragraph import Paragraph
    doc = Document(str(file))
    out: list[str] = []
    for child in doc.element.body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            para = Paragraph(child, doc)
            text = para.text.strip()
            if not text:
                continue
            style = (para.style.name if para.style is not None else "") or ""
            m = re.match(r"Heading (\d)", style)
            if m:
                out.append("#" * int(m.group(1)) + " " + text)
            elif style == "Title":
                out.append("# " + text)
            elif "List Bullet" in style or text.startswith(("•", "-")):
                out.append("- " + text.lstrip("•- ").strip())
            elif "List Number" in style or re.match(r"^\d+[.)]\s", text):
                out.append(("1. " + text) if "List Number" in style else text)
            else:
                out.append(text)
            out.append("")
        elif tag == "tbl":
            rows = [[c.text.strip().replace("\n", " ").replace("|", "/") for c in r.cells]
                    for r in Table(child, doc).rows]
            if rows:
                out.append("| " + " | ".join(rows[0]) + " |")
                out.append("|" + "---|" * len(rows[0]))
                out.extend("| " + " | ".join(r) + " |" for r in rows[1:])
                out.append("")
    return "\n".join(out).strip() + "\n"


def convert(path: str, to: str, out: str | None = None) -> dict:
    """Convert a document: docx/pptx -> pdf, docx -> md/txt, pdf -> txt/md/docx."""
    from tools.documents import create
    file = resolve_path(path)
    if not file.exists():
        raise OpError(f"File not found: {file}")
    src, dst = file.suffix.lower(), "." + str(to or "").lower().lstrip(".")
    if src == dst:
        raise OpError(f"{file.name} already is a {dst.lstrip('.').upper()}.")
    note = ""
    if dst == ".pdf" and src in (".docx", ".doc", ".pptx", ".ppt", ".rtf", ".odt"):
        app = "PowerPoint.Application" if src in (".pptx", ".ppt") else "Word.Application"
        target = _converted(out, file, ".pdf")
        if _office_available(app):
            _office_convert(app, file, target)
        elif src == ".docx":
            create.write_pdf(target, docx_to_markdown(file), create.style_for("plain"), title=file.stem)
            note = " Word isn't installed, so this was made from the document's text: images and fine layout are simplified."
        else:
            raise OpError(f"Converting {src} to PDF needs {app.split('.')[0]}, which isn't installed here. "
                          "Open it in a program that has it and save as PDF.")
    elif src == ".docx" and dst in (".md", ".txt"):
        target = _converted(out, file, dst)
        text = docx_to_markdown(file)
        if dst == ".txt":
            text = re.sub(r"^#+\s*", "", text, flags=re.M)
        target.write_text(text, encoding="utf-8")
    elif src == ".pdf" and dst in (".txt", ".md", ".docx"):
        doc = _pages.open_doc(str(file))
        chunks = []
        wants_ocr = False
        for n in range(1, doc.count + 1):
            if doc.needs_ocr(n):
                wants_ocr = True
        if wants_ocr:
            doc.read_by_ocr([n for n in range(1, doc.count + 1)], __import__("time").monotonic() + 120)
        for n in range(1, doc.count + 1):
            text, _how = doc.text(n)
            chunks.append(text.strip())
        body = "\n\n".join(c for c in chunks if c)
        if not body:
            raise OpError(f"No text could be read from {file.name}.")
        target = _converted(out, file, dst)
        if dst == ".docx":
            paragraphs = [re.sub(r"\s*\n\s*", " ", p).strip() for p in re.split(r"\n\s*\n", body)]
            create.write_docx(target, "\n\n".join(p for p in paragraphs if p), create.style_for("plain"), title=file.stem)
            note = " Only the text came across: the PDF's layout, images and tables aren't kept."
        else:
            target.write_text(body, encoding="utf-8")
    else:
        raise OpError(f"I can't convert {src or 'that'} to {dst}. I convert Word or PowerPoint to PDF, "
                      "Word to Markdown or text, and PDF to text or Word.")
    back = _pages.info(str(target)) if target.suffix.lower() in (".pdf", ".docx") else {"count": 1, "unit": "file"}
    return {"path": str(target), "result": f"Converted {file.name} to {target.name}."
            + (f" ({back['count']} {back['unit']}s.)" if target.suffix.lower() in (".pdf", ".docx") else "") + note}


# ── one entrance ─────────────────────────────────────────────

def run(action: str, **args) -> dict:
    """The single door the tool goes through: a plain dict back, errors as words."""
    try:
        action = (action or "").lower().strip()
        table = {
            "merge": lambda: merge(args.get("paths") or [], args.get("out")),
            "extract": lambda: extract(args.get("path", ""), args.get("pages"), args.get("out")),
            "delete_pages": lambda: delete_pages(args.get("path", ""), args.get("pages"), args.get("out")),
            "rotate": lambda: rotate(args.get("path", ""), args.get("degrees", 90), args.get("pages"), args.get("out")),
            "reorder": lambda: reorder(args.get("path", ""), args.get("order") or args.get("pages"), args.get("out")),
            "split": lambda: split(args.get("path", ""), args.get("every"), args.get("ranges"), args.get("out_dir")),
            "compress": lambda: compress(args.get("path", ""), args.get("out")),
            "fields": lambda: form_fields(args.get("path", "")),
            "fill": lambda: fill_form(args.get("path", ""), args.get("values") or {}, args.get("out")),
            "from_images": lambda: from_images(args.get("paths") or [], args.get("out")),
            "info": lambda: info(args.get("path", "")),
            "convert": lambda: convert(args.get("path", ""), args.get("to", ""), args.get("out")),
        }
        if action not in table:
            return {"status": "error", "retry_safe": True,
                    "error": f"Unknown pdf action '{action}'. Actions: " + ", ".join(table)}
        return {"status": "success", **table[action]()}
    except OpError as exc:
        return {"status": "error", "error": str(exc), "retry_safe": True}
    except FileNotFoundError as exc:
        return {"status": "error", "error": str(exc), "retry_safe": True}
    except PermissionError:
        return {"status": "error", "retry_safe": False,
                "error": "A file involved is open in another program, so it can't be written. Close it and try again."}
    except Exception as exc:
        logger.exception("PDF operation %s failed", action)
        return {"status": "error", "retry_safe": False, "error": f"{action} failed: {exc}"}
