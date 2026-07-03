from tools.email.gmail_client import GmailClient

gmail = GmailClient()


def send_email(
    to: str,
    subject: str,
    body: str
) -> str:

    message_id = gmail.send_email(
        to=to,
        subject=subject,
        body=body
    )

    return f"Email sent successfully. Message ID: {message_id}"


def read_email(
    max_results: int = 10
):

    return gmail.read_email(
        max_results=max_results
    )