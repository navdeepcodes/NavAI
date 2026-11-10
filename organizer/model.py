"""Ask the local model the one question it is good at: what is this file,
and what should it be called?

The model never moves anything. It returns a suggested title and an optional
topic, both of which are cleaned, length-limited and allowed to be ignored.
Any failure -- no Ollama, no model, a timeout, a reply that isn't JSON --
returns None and the rule-based plan stands. A missing model must make the
organizer less clever, never broken.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from organizer.classify import clean_stem
from organizer.scan import FileEntry

# Categories whose contents are worth reading. Images go through vision only
# when the caller opts in, because vision costs seconds per file.
READABLE_CATEGORIES = frozenset({"Documents", "Spreadsheets", "Presentations", "Other"})
SNIPPET_CHARS = 1500
MAX_TOPIC_CHARS = 32

# Offered, not imposed: the model may name another topic, but a shared
# vocabulary keeps it from inventing "Bills", "Bill", and "Invoices" for the
# same kind of file in one run.
SUGGESTED_TOPICS = (
    "College", "Assignments", "Notes", "Research Papers", "Resumes",
    "Invoices & Receipts", "Bank & Finance", "Tickets & Travel", "IDs & Certificates",
    "Work", "Projects", "Manuals", "Books", "Forms",
)

_PROMPT = """You are sorting files in someone's Downloads folder.
Read the file details and reply with JSON only, exactly this shape:
{{"title": "...", "topic": "..."}}

title: a short, specific filename for this file WITHOUT the extension, 2-8 words,
  Title Case, no dates unless the date is what identifies it
  (e.g. "Flight Dynamics Assignment 3", "Swiggy Invoice March 2026", "Offer Letter Acme").
  If the current name is already clear and specific, return it unchanged.
topic: one subfolder this file belongs in, 1-3 words. Prefer one of:
  {topics}.
  Use "" if none fits well.

Current filename: {name}
Type: {category}
Content (may be cut off):
---
{snippet}
---"""


@dataclass
class Suggestion:
    title: str | None
    topic: str | None


class ModelNamer:
    def __init__(self, *, look_at_images: bool = False) -> None:
        from config import ollama as cfg

        self._model = cfg.OLLAMA_CHAT_MODEL
        self._vision_model = cfg.OLLAMA_VISION_MODEL
        self._host = cfg.OLLAMA_HOST
        # Same context size as the chat path, so a model Mike already has
        # resident answers directly instead of being reloaded for a
        # different runner (see describe_image in ollama_provider.py).
        self._num_ctx = cfg.NUM_CTX
        self._keep_alive = cfg.KEEP_ALIVE
        self._look_at_images = look_at_images
        self._client = None

    # ── availability ───────────────────────────────────────

    def unavailable_reason(self) -> str | None:
        """None when the model can be used, otherwise a sentence saying why
        the plan falls back to rules."""
        try:
            import ollama

            self._client = ollama.Client(host=self._host, timeout=60)
            listed = self._client.list()
        except Exception:
            self._client = None
            return "Ollama isn't running, so files are sorted by type only."
        names = {getattr(m, "model", None) for m in listed.models}
        if self._model not in names and f"{self._model}:latest" not in names:
            self._client = None
            return f"The {self._model} model isn't downloaded yet, so files are sorted by type only."
        return None

    def wants(self, category: str) -> bool:
        if category in READABLE_CATEGORIES:
            return True
        return self._look_at_images and category in ("Images", "Screenshots")

    # ── the question ───────────────────────────────────────

    def suggest(self, entry: FileEntry, category: str) -> Suggestion | None:
        if self._client is None:
            return None
        try:
            if category in ("Images", "Screenshots"):
                reply = self._ask(entry, category, "(an image -- judge it by what it shows)",
                                  model=self._vision_model, image=entry.path)
            else:
                snippet = _snippet(entry.path)
                if snippet is None:
                    return None
                reply = self._ask(entry, category, snippet or "(no readable text)",
                                  model=self._model)
        except Exception:
            return None
        return _parse(reply)

    def _ask(self, entry: FileEntry, category: str, snippet: str, *,
             model: str, image: Path | None = None) -> str:
        prompt = _PROMPT.format(
            topics=", ".join(SUGGESTED_TOPICS),
            name=entry.name,
            category=category,
            snippet=snippet,
        )
        message: dict = {"role": "user", "content": prompt}
        if image is not None:
            message["images"] = [str(image)]
        response = self._client.chat(
            model=model,
            messages=[message],
            format="json",
            think=False,
            keep_alive=self._keep_alive,
            options={"temperature": 0.1, "num_ctx": self._num_ctx, "num_predict": 80},
        )
        return response.message.content or ""


def _snippet(path: Path) -> str | None:
    """The start of a file's text, or "" when it has none worth reading
    (the model still sees the name), or None when reading it failed in a way
    that means the model shouldn't be asked at all."""
    from tools.filesystem.document_reader import DocumentUnreadable, read_document

    try:
        text = read_document(str(path))
    except DocumentUnreadable:
        return ""
    except Exception:
        return None
    return text[:SNIPPET_CHARS]


def _parse(reply: str) -> Suggestion | None:
    try:
        data = json.loads(reply)
    except (TypeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    title = clean_stem(str(data.get("title") or ""))
    topic = clean_stem(str(data.get("topic") or ""))[:MAX_TOPIC_CHARS].strip()
    return Suggestion(title=title or None, topic=topic or None)
