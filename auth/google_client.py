import json
from functools import lru_cache
from pathlib import Path

from google.oauth2.credentials import Credentials

from auth.token_store import TOKEN_FILE

SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/drive.file",
]


@lru_cache(maxsize=1)
def get_credentials() -> Credentials:
    """Load cached credentials from the token file.

    Uses from_authorized_user_info() to correctly parse the
    JSON structure produced by Credentials.to_json().
    """
    token_path = Path(TOKEN_FILE)
    if not token_path.exists():
        raise FileNotFoundError(
            f"Token file not found at {TOKEN_FILE}. "
            "Run auth.oauth.login() first."
        )

    with token_path.open("r") as f:
        token_data = json.load(f)

    return Credentials.from_authorized_user_info(token_data, SCOPES)
