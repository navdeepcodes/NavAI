"""The Privacy Policy, Terms of Use and open-source licences, as shipped.

The documents live in docs/legal as Markdown with a few {placeholders} filled
from config.settings, so the publisher, website and version are stated once
and every document agrees. Found beside the frozen app or in the source tree.
"""
from __future__ import annotations

import os
import sys

DOCS = {
    "privacy": ("Privacy Policy", "PRIVACY.md"),
    "terms": ("Terms of Use", "TERMS.md"),
    "licences": ("Open-source licences", "THIRD_PARTY_NOTICES.md"),
}


def _folder() -> str | None:
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for base in (getattr(sys, "_MEIPASS", ""), here):
        path = os.path.join(base, "docs", "legal")
        if base and os.path.isdir(path):
            return path
    return None


def title(key: str) -> str:
    return DOCS[key][0]


def load(key: str) -> str:
    """The document as Markdown, placeholders filled. Never raises."""
    from config import settings
    folder = _folder()
    text = ""
    if folder:
        try:
            with open(os.path.join(folder, DOCS[key][1]), encoding="utf-8") as fh:
                text = fh.read()
        except OSError:
            text = ""
    if not text:
        return f"# {title(key)}\n\nThis document couldn't be found in this installation."
    try:
        from hostplatform import storage
        data_dir = str(storage.data_dir())
    except Exception:
        data_dir = "Mike's data folder"
    contact = (f"email {settings.SUPPORT_EMAIL} or visit {settings.WEBSITE}"
               if getattr(settings, "SUPPORT_EMAIL", "") else f"visit {settings.WEBSITE}")
    from datetime import date
    try:
        # LEGAL_VERSION is a date, optionally with a revision ("2026-09-25.2").
        updated = date.fromisoformat(settings.LEGAL_VERSION[:10]).strftime("%d %B %Y").lstrip("0")
    except Exception:
        updated = settings.LEGAL_VERSION
    try:
        from account import config as account_config
        required = account_config.required()
    except Exception:
        required = False
    account_terms = ("You need a Mike account to use this copy of Mike." if required else
                     "You don't need an account to use Mike.")
    values = {
        "publisher": settings.PUBLISHER, "website": settings.WEBSITE,
        "version": settings.VERSION, "updated": updated,
        "data_dir": data_dir, "contact": contact, "account_terms": account_terms,
    }
    for k, v in values.items():
        text = text.replace("{" + k + "}", v)
    return text


def accepted() -> bool:
    from config import preferences, settings
    return str(preferences.get("terms_accepted_version", "") or "") == settings.LEGAL_VERSION


def accept() -> None:
    from config import preferences, settings
    preferences.set_value("terms_accepted_version", settings.LEGAL_VERSION)
