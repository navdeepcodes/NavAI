from functools import lru_cache

from google.oauth2.credentials import Credentials

from auth.token_store import TOKEN_FILE


SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/drive.file"
]


@lru_cache(maxsize=1)
def get_credentials() -> Credentials:
    """Load and cache Google OAuth credentials from the token file."""
    return Credentials.from_authorized_user_file(
        TOKEN_FILE,
        SCOPES
    )
