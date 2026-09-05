import os

from tools.email.gmail_client import GmailClient


def main():
    # Requires an explicit, real recipient on purpose — this sends a real,
    # irreversible email through whatever Gmail account is connected. There
    # is no safe default recipient for that, so none is provided.
    to = os.environ.get("MIKE_TEST_GMAIL_RECIPIENT")
    if not to:
        print(
            "Skipped: this sends a real email. Set MIKE_TEST_GMAIL_RECIPIENT "
            "to a real address you control and run this file directly to use it."
        )
        return

    gmail = GmailClient()
    gmail.send_email(
        to=to,
        subject="Mike Test",
        body="Hello from Mike 🚀"
    )
    print("Email sent!")


if __name__ == "__main__":
    # Manual smoke test only, and only with an explicit recipient — guarded
    # so pytest collection can't trigger a real send by just importing the
    # file, which is exactly what used to happen.
    main()
