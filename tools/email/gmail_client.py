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

    def send_email(
        self,
        to: str,
        subject: str,
        body: str
    ) -> bool:

        message = MIMEText(body)

        message["to"] = to
        message["subject"] = subject

        raw = base64.urlsafe_b64encode(
            message.as_bytes()
        ).decode()

        self.service.users().messages().send(

            userId="me",

            body={
                "raw": raw
            }

        ).execute()

        return True