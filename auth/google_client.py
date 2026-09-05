import json
from functools import lru_cache
from pathlib import Path

from google.oauth2.credentials import Credentials

from auth.token_store import TOKEN_FILE

SCOPES = [
    # Only what email actually needs. The previous list also asked for
    # calendar and drive.file, which nothing here uses -- a consent screen
    # should ask for the access the feature requires and nothing more, and a
    # narrower request is a smaller thing to trust.
    #
    # gmail.send    to send.
    # gmail.readonly to read the sent message back and confirm the recipient
    #               and attachment actually went, which is the whole basis of
    #               verifying rather than trusting the returned message id.
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
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
