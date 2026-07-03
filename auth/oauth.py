from google_auth_oauthlib.flow import InstalledAppFlow

from auth.token_store import save


SCOPES = [

    "https://www.googleapis.com/auth/gmail.send",

    "https://www.googleapis.com/auth/gmail.readonly",

    "https://www.googleapis.com/auth/calendar",

    "https://www.googleapis.com/auth/drive.file"

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