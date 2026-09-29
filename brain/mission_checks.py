"""What a piece of work actually contains — read from the file, not claimed.

A mission's progress is only worth showing if it is true. These functions look
at the document the user is writing and report its real shape: how many words,
which sections exist, how much is written under each. Nothing here calls the
model, so checking costs milliseconds and can run every time the file is saved.

Headings are recognised the way people actually write them: a Word "Heading"
style, or a short bold line ("Results"), or a Markdown "#", or a short line
ending in a colon. Numbering is ignored, so "2. Results:" is the section
"Results".
"""
from __future__ import annotations

import os
import re
from pathlib import Path

_WORD = re.compile(r"[A-Za-z0-9À-ɏ][\w'’\-]*")
_NUMBERING = re.compile(r"^\s*(?:\d+(?:\.\d+)*|[IVXivx]+|[A-Za-z])[.)]\s+")

#: A section with no target from the brief counts as written at this length.
DEFAULT_MIN_WORDS = 25
#: Formats a person writes in; anything else is only ever read (a brief).
WRITABLE = {".docx", ".md", ".txt"}
#: How much of a section's text travels with the mission, so Mike can coach
#: the next part from what was actually written without reading the file.
EXCERPT_CHARS = 360


#: A document this short is described in its own words: usually a brief, and
#: its words are what a plan is made from.
WHOLE_WORDS = 250


def needed(target: int) -> int:
    """Words that count as a section written. Briefs say "about 150 words";
    29 words against "about 30" is a finished Aim, so 90% of the target is
    enough -- the true count is still what's shown."""
    return max(1, -(-int(target) * 9 // 10))


def count_words(text: str) -> int:
    return len(_WORD.findall(text or ""))


def section_name(text: str) -> str:
    """'2. Results:' -> 'Results'."""
    name = _NUMBERING.sub("", (text or "").strip())
    return name.rstrip(":").strip()


def _looks_like_heading(text: str) -> bool:
    words = text.split()
    return 0 < len(words) <= 6 and not text.rstrip().endswith((".", "?", "!", ","))


def paragraph_kind(p) -> str:
    """'title', 'heading' or 'text' for a python-docx paragraph."""
    text = p.text.strip()
    style = (p.style.name or "") if p.style is not None else ""
    if style.lower() == "title":
        return "title"
    runs = [r for r in p.runs if r.text.strip()]
    bold_line = bool(runs) and all(r.bold for r in runs)
    if style.lower().startswith("heading") or (text and bold_line and _looks_like_heading(text)):
        return "heading"
    return "text"


def _docx_blocks(path: Path) -> list[tuple[bool, str]]:
    from docx import Document

    blocks = []
    for p in Document(str(path)).paragraphs:
        text = p.text.strip()
        if not text:
            continue
        kind = paragraph_kind(p)
        if kind == "title":
            continue                      # the document's title, not a section
        blocks.append((kind == "heading", text))
    return blocks


def _text_blocks(path: Path) -> list[tuple[bool, str]]:
    blocks = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        text = line.strip()
        if not text:
            continue
        if text.startswith("#"):
            blocks.append((True, text.lstrip("#").strip()))
        elif text.endswith(":") and _looks_like_heading(text[:-1]):
            blocks.append((True, text))
        else:
            blocks.append((False, text))
    return blocks


def outline(path: str) -> dict | None:
    """The document's real shape, or None if it does not exist.

    {"words": 812, "mtime": 1727.., "sections": {"Results": 180, ...},
     "order": ["Aim", "Method", "Results"]}  -- or {"error": "..."} when the
    file exists but cannot be read (open in another app, corrupt).
    """
    file = Path(path)
    if not file.exists():
        return None
    try:
        mtime = os.path.getmtime(file)
        suffix = file.suffix.lower()
        if suffix == ".docx":
            blocks = _docx_blocks(file)
        elif suffix in (".md", ".txt"):
            blocks = _text_blocks(file)
        else:
            from tools.filesystem.document_reader import read_document
            return {"words": count_words(read_document(str(file))), "mtime": mtime,
                    "sections": {}, "order": []}
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"[:200]}

    sections: dict[str, int] = {}
    excerpts: dict[str, str] = {}
    order: list[str] = []
    current: str | None = None
    total = 0
    for heading, text in blocks:
        if heading:
            current = section_name(text)
            if current and current not in sections:
                sections[current] = 0
                order.append(current)
            continue
        words = count_words(text)
        total += words
        if current:
            sections[current] = sections.get(current, 0) + words
            if len(excerpts.get(current, "")) < 20_000:
                excerpts[current] = (excerpts.get(current, "") + " " + text).strip()
    return {"words": total, "mtime": mtime, "sections": sections, "order": order,
            "excerpts": {k: _head_and_tail(v) for k, v in excerpts.items()}}


def _head_and_tail(text: str) -> str:
    """What a section says, in EXCERPT_CHARS: its sentences with figures in
    them first (a result, a measurement, a date), then its opening. Measured,
    an excerpt of just the start -- and then of the start and end -- both
    left out the student's value of g, and Mike had to ask them for it."""
    if len(text) <= EXCERPT_CHARS:
        return text
    sentences = re.split(r"(?<=[.!?])\s+", text)
    numeric = [s for s in sentences if re.search(r"\d", s)]
    picked, used = [], 0
    for s in numeric + [s for s in sentences if s not in numeric]:
        if used + len(s) + 1 > EXCERPT_CHARS:
            continue
        picked.append(s)
        used += len(s) + 1
    if not picked:
        return text[:EXCERPT_CHARS].rstrip() + "…"
    order = {s: i for i, s in enumerate(sentences)}
    return " … ".join(sorted(picked, key=order.get)) if len(picked) > 1 else picked[0]


def find_section(sections: dict[str, int], name: str) -> str | None:
    """The document's own heading for a section name, matched loosely."""
    wanted = section_name(name).casefold()
    if not wanted:
        return None
    for heading in sections:
        if heading.casefold() == wanted:
            return heading
    for heading in sections:
        h = heading.casefold()
        if re.search(rf"(?<!\w){re.escape(wanted)}(?!\w)", h) or re.search(rf"(?<!\w){re.escape(h)}(?!\w)", wanted):
            return heading
    return None


def brief_headings(text: str) -> list[str]:
    """Section names an assignment brief asks for: short title-like lines,
    and the names in lines like 'Results (about 150 words)'."""
    found: list[str] = []
    for raw in (text or "").splitlines():
        line = raw.strip().strip("-*• ").strip()
        if not line:
            continue
        head = re.split(r"\s*[(–—:]|\s+-\s+", line, maxsplit=1)[0]
        name = section_name(head)
        if name and _looks_like_heading(name) and name[0].isupper() and len(name) <= 40:
            if name not in found and not name.lower().startswith(("page", "due", "total")):
                found.append(name)
    return found


def target_words(brief: str, section: str) -> int | None:
    """The length the brief asks for a section, e.g. 'Results (about 150
    words)' or 'Discussion: 150-200 words' -> the lower bound."""
    for line in (brief or "").splitlines():
        if find_section({section_name(re.split(r"[(:–—]", line.strip(), maxsplit=1)[0]): 0}, section):
            m = re.search(r"(\d{2,4})\s*(?:-|–|to)\s*\d{2,4}\s*words|(\d{2,4})\s*words", line, re.I)
            if m:
                return int(m.group(1) or m.group(2))
    return None


def guidance(brief: str, section: str, limit: int = 220) -> str:
    """What the brief says about a section, e.g. 'Discussion (150-200 words)
    - compare your g with 9.81 m/s2 and explain the main sources of error.'
    Carried with the step so Mike can coach it without re-reading the brief."""
    for line in (brief or "").splitlines():
        head = section_name(re.split(r"[(:–—]|\s+-\s+", line.strip(), maxsplit=1)[0])
        if head and find_section({head: 0}, section) and len(line.strip()) > len(head) + 3:
            text = " ".join(line.split())
            return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"
    return ""


def link_step(title: str, headings: list[str]) -> str | None:
    """The section a step is about: 'Write the Results section' -> 'Results'.
    The longest heading named in the step wins."""
    t = title.casefold()
    best = None
    for h in headings:
        name = section_name(h)
        if name and re.search(rf"(?<!\w){re.escape(name.casefold())}(?!\w)", t):
            if best is None or len(name) > len(best):
                best = name
    return best


def describe_changes(old: dict | None, new: dict | None, label: str) -> list[str]:
    """What changed in one file between two outlines, in plain words."""
    if not new or "error" in new:
        return []
    if not old or "error" in old:
        return []
    out = []
    for name in new.get("order", []):
        before, after = old.get("sections", {}).get(name), new["sections"][name]
        if before is None and after:
            out.append(f"{name} added ({after} words)")
        elif before is not None and after != before:
            out.append(f"{name}: {before} → {after} words")
    if not out and new.get("words") != old.get("words"):
        out.append(f"{label}: {old.get('words', 0)} → {new.get('words', 0)} words")
    return out


def describe_file(path) -> str:
    """One file as facts for the model: the sections of a document someone
    writes in and how much is under each, or a short document's own words."""
    file = Path(path)
    shape = outline(str(file))
    if shape is None:
        return f"{file}: not found"
    if "error" in shape:
        return f"{file}: can't be read right now ({shape['error']})"
    from tools.filesystem.document_reader import read_document

    # What it says, and for a document with headings how much is under each.
    # Measured: given only "sections: Essay: Photosynthesis (6 words)", the
    # model answered "what is this about?" with the structure, not the topic.
    sections = ", ".join(f"{h} ({shape['sections'][h]} words)" for h in shape["order"])
    sections = f"\nSections: {sections}." if sections else ""
    lines = [" ".join(line.split()) for line in read_document(str(file)).splitlines()]
    text = "\n".join(line for line in lines if line)
    words = count_words(text)
    if words <= WHOLE_WORDS:
        return f"{file} ({words} words):\n{text}{sections}"
    lead = " ".join(text.split()[:80])
    return f"{file} ({words} words), starts: {lead} … (read_document for the rest){sections}"
