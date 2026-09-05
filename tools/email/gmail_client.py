"""Gmail over the API.

Email is the case where a deterministic integration genuinely beats driving
the interface. Composing a message through a web UI means fighting recipient
autocomplete, focus stealing and a native file picker, and every one of those
is a chance to put the subject line into the To field. The API takes a
recipient, a subject, a body and a list of paths, and either works or returns
an error -- and it can be verified afterwards by reading the sent message back
out of the mailbox.

The general computer layer remains capable of driving webmail; it is the
fallback for accounts with no API access, not the first choice here.

This client previously sent a bare MIMEText with no way to attach anything,
which is why the whole capability could not satisfy a task that required an
attachment.
"""
from __future__ import annotations

import base64
import mimetypes
import os
from email.message import EmailMessage

from google.auth.exceptions import RefreshError
from googleapiclient.discovery import build

from auth.google_client import get_credentials

# Gmail rejects very large messages outright; fail before the upload rather
# than after it.
MAX_ATTACHMENT_BYTES = 20 * 1024 * 1024


class GmailAuthError(RuntimeError):
    """Raised when credentials are missing or no longer valid.

    Separate from other failures because the remedy is different and belongs
    to the user: nobody but the account holder can complete an OAuth consent.
    """


class GmailClient:

    def __init__(self) -> None:
        # Built lazily. The previous module created a client at import time,
        # which meant importing the email tools could trigger an auth flow --
        # a side effect no import should have.
        self._service = None

    @property
    def service(self):
        if self._service is None:
            try:
                self._service = build("gmail", "v1", credentials=get_credentials())
            except FileNotFoundError as exc:
                raise GmailAuthError(
                    "No Google token is stored. Run auth.oauth.login() to sign in."
                ) from exc
            except Exception as exc:
                raise GmailAuthError(self._auth_hint(exc)) from exc
        return self._service

    @staticmethod
    def _auth_hint(exc: Exception) -> str:
        detail = str(exc)
        if "invalid_grant" in detail:
            return (
                "The stored Google token is no longer valid — its refresh token "
                "has been revoked or expired. Only the account holder can fix "
                "this: run `venv/bin/python -c \"from auth.oauth import login; "
                "login()\"` and complete the consent screen in the browser."
            )
        return f"Google authentication failed: {detail[:200]}"

    def account(self) -> str:
        """Which mailbox this client is signed into."""
        try:
            profile = self.service.users().getProfile(userId="me").execute()
        except RefreshError as exc:
            raise GmailAuthError(self._auth_hint(exc)) from exc
        return profile.get("emailAddress", "")

    # ── sending ───────────────────────────────────────────

    def build_message(self, to: str, subject: str, body: str,
                      attachments: list[str] | None = None) -> EmailMessage:
        """Assemble the message, including attachments.

        Kept separate from sending so a caller can inspect exactly what would
        go out before anything leaves the machine — which is what makes a
        meaningful confirmation possible.
        """
        message = EmailMessage()
        message["To"] = to
        message["Subject"] = subject
        message.set_content(body)

        for path in (attachments or []):
            resolved = os.path.abspath(os.path.expanduser(path))
            if not os.path.isfile(resolved):
                raise FileNotFoundError(f"Attachment not found: {resolved}")
            size = os.path.getsize(resolved)
            if size > MAX_ATTACHMENT_BYTES:
                raise ValueError(
                    f"{os.path.basename(resolved)} is {size / 1_048_576:.1f} MB, "
                    f"over Gmail's {MAX_ATTACHMENT_BYTES // 1_048_576} MB limit."
                )
            guessed, _ = mimetypes.guess_type(resolved)
            maintype, _, subtype = (guessed or "application/octet-stream").partition("/")
            with open(resolved, "rb") as handle:
                message.add_attachment(
                    handle.read(), maintype=maintype, subtype=subtype or "octet-stream",
                    filename=os.path.basename(resolved),
                )
        return message

    def send_email(self, to: str, subject: str, body: str,
                   attachments: list[str] | None = None) -> str:
        message = self.build_message(to, subject, body, attachments)
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        # A stale refresh token does not fail when the client is built -- the
        # refresh happens on the first real request, so the auth failure
        # arrives here rather than in the constructor. Translating it means
        # the caller learns the remedy is a human consent flow, not a retry.
        try:
            response = self.service.users().messages().send(
                userId="me", body={"raw": raw},
            ).execute()
        except RefreshError as exc:
            raise GmailAuthError(self._auth_hint(exc)) from exc
        return response["id"]

    # ── verification ──────────────────────────────────────

    def describe_sent(self, message_id: str) -> dict:
        """Read a sent message back out of the mailbox.

        Verification has to come from the mailbox rather than from the send
        call returning an id: an id proves a request was accepted, not that
        the message carries the recipient and attachment intended.
        """
        message = self.service.users().messages().get(
            userId="me", id=message_id, format="full",
        ).execute()

        headers = {h["name"].lower(): h["value"]
                   for h in message.get("payload", {}).get("headers", [])}

        filenames: list[str] = []

        def collect(part):
            if part.get("filename"):
                filenames.append(part["filename"])
            for child in part.get("parts", []) or []:
                collect(child)

        collect(message.get("payload", {}))

        return {
            "id": message_id,
            "to": headers.get("to", ""),
            "subject": headers.get("subject", ""),
            "labels": message.get("labelIds", []),
            "attachments": filenames,
            "in_sent": "SENT" in message.get("labelIds", []),
        }

    # No read_email here. Reading a mailbox is a real capability with real
    # design questions -- which mailbox, how much, what shape the result takes,
    # and how much of someone's private mail should enter a model's context.
    # A method that raises NotImplementedError answers none of them while
    # advertising that it might.
