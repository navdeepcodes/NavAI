"""The document tools as Mike's runtime calls them: arguments in, a plain dict out.

Every function here returns {"status": "success"|"error", ...} and never
raises: a failure is words the model can act on (and the student can be told),
not a stack trace.
"""
from __future__ import annotations

from logs.logger import logger
from tools.filesystem.document_reader import DocumentUnreadable


def _guard(name: str, fn, args: dict) -> dict:
    try:
        return fn(args)
    except FileNotFoundError as exc:
        return {"status": "error", "error": str(exc), "retry_safe": True}
    except DocumentUnreadable as exc:
        # The file is there and the path is right; the format or the file
        # itself is the problem, so retrying the same call cannot help.
        return {"status": "error", "error": str(exc), "retry_safe": False}
    except PermissionError:
        return {"status": "error", "retry_safe": False,
                "error": "That file is open in another program, or Mike isn't allowed to read it."}
    except Exception as exc:
        logger.exception("Document tool %s failed", name)
        return {"status": "error", "retry_safe": False,
                "error": f"Could not do that with the document: {exc}"}


def _read(args: dict) -> dict:
    from tools.documents import pages
    path = str(args.get("path") or "").strip()
    if not path:
        return {"status": "error", "error": "No file path provided.", "retry_safe": True}
    got = pages.read(path, args.get("pages"))
    if got.get("status") != "success":
        return got
    unit = got["unit"]
    footer = [f"[{unit.capitalize()}{'s' if ',' in got['shown'] or '-' in got['shown'] else ''} {got['shown']} "
              f"of {got['total']}.]"]
    if got.get("next"):
        footer.append(f"[Next: read_document with pages {got['next']} for the rest.]")
    footer.extend(got.get("notes") or [])
    got["result"] = got["text"] + "\n\n" + "\n".join(footer)
    return got


def read_document(args: dict) -> dict:
    return _guard("read_document", _read, args)


def document_info(args: dict) -> dict:
    from tools.documents import pages
    return _guard("document_info", lambda a: pages.info(str(a.get("path") or "")), args)


def search_document(args: dict) -> dict:
    from tools.documents import pages

    def go(a: dict) -> dict:
        return pages.search(str(a.get("query") or ""), str(a.get("path") or "."),
                            regex=bool(a.get("regex")), max_results=int(a.get("max_results") or 15))
    return _guard("search_document", go, args)


def create_document(args: dict) -> dict:
    from tools.documents import create

    def go(a: dict) -> dict:
        return create.create(
            str(a.get("path") or ""), str(a.get("content") or ""), a.get("style"),
            title=str(a.get("title") or ""), author=str(a.get("author") or ""),
            overwrite=bool(a.get("overwrite")), toc=bool(a.get("toc")),
            font=a.get("font"), size=a.get("font_size"), line_spacing=a.get("line_spacing"),
            page_size=(str(a.get("page_size")).lower() if a.get("page_size") else None))
    return _guard("create_document", go, args)


def create_presentation(args: dict) -> dict:
    from tools.documents import slides

    def go(a: dict) -> dict:
        return slides.create_deck(str(a.get("path") or ""), str(a.get("title") or ""), a.get("slides") or [],
                                  theme=str(a.get("theme") or "graphite"), author=str(a.get("author") or ""),
                                  overwrite=bool(a.get("overwrite")))
    return _guard("create_presentation", go, args)


def pdf_edit(args: dict) -> dict:
    from tools.documents import pdf_ops

    def go(a: dict) -> dict:
        rest = {k: v for k, v in a.items() if k != "action"}
        return pdf_ops.run(str(a.get("action") or ""), **rest)
    return _guard("pdf_edit", go, args)


TOOLS = {
    "read_document": read_document,
    "document_info": document_info,
    "search_document": search_document,
    "create_document": create_document,
    "create_presentation": create_presentation,
    "pdf_edit": pdf_edit,
}
