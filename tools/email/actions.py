"""Email actions exposed through the tool registry.

Only send_email is here. read_email was listed as an available action while
its implementation raised NotImplementedError, so the capability surface
advertised something that could only fail. An unimplemented capability is
worse than a missing one: a caller plans around it and finds out at the point
of use.

It comes back when there is a real implementation behind it.
"""
from tools.email.gmail_client import GmailClient

# Constructed at import, which is safe now only because GmailClient defers
# authentication until its first request. It previously built an API client
# here, so importing this module could start a browser consent flow.
gmail = GmailClient()


def send_email(to: str, subject: str, body: str,
               attachments: list[str] | None = None) -> str:
    message_id = gmail.send_email(
        to=to, subject=subject, body=body, attachments=attachments,
    )
    return f"Email sent successfully. Message ID: {message_id}"
