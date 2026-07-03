import json
from pathlib import Path


SESSION_DIR = Path(__file__).parent / "conversations"
SESSION_FILE = SESSION_DIR / "session.json"


class SessionMemory:

    def __init__(self):

        SESSION_DIR.mkdir(
            parents=True,
            exist_ok=True
        )

        self.messages = []

        self.load()

    def add(
        self,
        role,
        content
    ):

        self.messages.append({

            "role": role,

            "content": content

        })

        self.save()

    def last(
        self,
        limit=20
    ):

        return self.messages[-limit:]

    def clear(self):

        self.messages = []

        self.save()

    def save(self):

        with open(

            SESSION_FILE,

            "w",

            encoding="utf-8"

        ) as f:

            json.dump(

                self.messages,

                f,

                indent=4,

                ensure_ascii=False

            )

    def load(self):

        if not SESSION_FILE.exists():

            self.messages = []

            self.save()

            return

        try:

            with open(

                SESSION_FILE,

                "r",

                encoding="utf-8"

            ) as f:

                self.messages = json.load(f)

        except (

            json.JSONDecodeError,

            FileNotFoundError

        ):

            self.messages = []

            self.save()