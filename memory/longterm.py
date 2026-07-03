from pathlib import Path


KNOWLEDGE = Path(__file__).parent / "knowledge"


class LongTermMemory:

    def __init__(self):

        KNOWLEDGE.mkdir(
            exist_ok=True
        )

    def save(

        self,

        category,

        text

    ):

        file = KNOWLEDGE / f"{category}.md"

        existing = ""

        if file.exists():

            existing = file.read_text(
                encoding="utf-8"
            )

        if text in existing:

            return

        with open(

            file,

            "a",

            encoding="utf-8"

        ) as f:

            f.write(text.strip() + "\n")

    def read(

        self,

        category

    ):

        file = KNOWLEDGE / f"{category}.md"

        if not file.exists():

            return ""

        return file.read_text(

            encoding="utf-8"

        )