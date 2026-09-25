"""Where Mike's Supabase project is, read from config.settings at call time.

Accounts are off — and every account surface hidden — until a project URL and
its public (anon or publishable) key are set. Both are safe to ship in the
app: the key only identifies the project, and row-level security decides
what anyone can read or change (supabase/migrations).
"""
from __future__ import annotations


def url() -> str:
    from config import settings
    return str(getattr(settings, "SUPABASE_URL", "") or "").strip().rstrip("/")


def anon_key() -> str:
    from config import settings
    return str(getattr(settings, "SUPABASE_ANON_KEY", "") or "").strip()


def configured() -> bool:
    return bool(url() and anon_key())


def oauth_providers() -> list[str]:
    """Sign-in providers turned on in the Supabase project (e.g. ["google"])."""
    from config import settings
    raw = getattr(settings, "SUPABASE_OAUTH_PROVIDERS", ()) or ()
    if isinstance(raw, str):
        raw = raw.split(",")
    return [p.strip().lower() for p in raw if p and p.strip()]


def required() -> bool:
    """Whether Mike can only be used signed in. Off by default: Mike works
    fully on its own, and an account is something you choose."""
    from config import settings
    return configured() and bool(getattr(settings, "ACCOUNT_REQUIRED", False))
