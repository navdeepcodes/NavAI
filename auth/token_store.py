import json
import os

TOKEN_FILE = "storage/token.json"


def save(credentials):

    with open(TOKEN_FILE, "w") as f:
        f.write(credentials.to_json())


def exists():

    return os.path.exists(TOKEN_FILE)