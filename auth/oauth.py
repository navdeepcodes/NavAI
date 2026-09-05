from google_auth_oauthlib.flow import InstalledAppFlow

from auth.token_store import save


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


def login():

    flow = InstalledAppFlow.from_client_secrets_file(

        "credentials.json",

        SCOPES

    )

    credentials = flow.run_local_server(

        port=0

    )

    save(credentials)

    print("✅ Google login successful.")