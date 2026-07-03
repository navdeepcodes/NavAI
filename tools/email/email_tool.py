from tools.email.gmail_client import GmailClient


gmail = GmailClient()


def send_email(
    to: str,
    subject: str,
    body: str
):
    """
    Send an email.

    Args:
        to: Recipient email address.
        subject: Email subject.
        body: Email body.
    """

    gmail.send_email(
        to=to,
        subject=subject,
        body=body
    )

    return f"Email sent successfully to {to}."