from __future__ import annotations

import base64
from email.mime.text import MIMEText

from googleapiclient.discovery import build

from auth.google_client import get_credentials


class GmailClient:

    def __init__(self):

        self.service = build(
            "gmail",
            "v1",
            credentials=get_credentials()
        )

    # ---------------------------------------------------------

    def send_email(
        self,
        to: str,
        subject: str,
        body: str
    ) -> str:

        message = MIMEText(body)

        message["to"] = to
        message["subject"] = subject

        raw = base64.urlsafe_b64encode(
            message.as_bytes()
        ).decode()

        response = self.service.users().messages().send(

            userId="me",

            body={
                "raw": raw
            }

        ).execute()

        return response["id"]

    # ---------------------------------------------------------

    def read_email(
        self,
        max_results: int = 10
    ):

        raise NotImplementedError(
            "read_email() not implemented yet."
        )