"""Where the Gmail OAuth token lives on disk."""
from __future__ import annotations

from hostplatform import storage

# Used to be the literal string "storage/token.json" — relative to whatever
# directory the process was launched from. It carried the single most
# sensitive credential Mike holds, and it lived next to the source rather than
# in the same per-user data directory as everything else. See
# hostplatform/storage.py for why that class of bug matters and how the three
# instances of it were fixed together.
TOKEN_FILE = str(storage.token_path())


def save(credentials) -> None:
    storage.token_path().write_text(credentials.to_json())


def exists() -> bool:
    return storage.token_path().exists()
