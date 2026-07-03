from pathlib import Path


KNOWLEDGE = Path(__file__).parent / "knowledge"


class MemoryRetriever:

    def __init__(self):

        KNOWLEDGE.mkdir(
            exist_ok=True
        )

    def retrieve(
        self,
        limit=10
    ):

        memories = []

        for file in KNOWLEDGE.glob("*.md"):

            try:

                text = file.read_text(
                    encoding="utf-8"
                )

                if not text.strip():
                    continue

                memories.append(

                    f"[{file.stem.upper()}]\n{text}"

                )

            except Exception:

                continue

        return "\n\n".join(
            memories[:limit]
        )

    def retrieve_category(
        self,
        category
    ):

        file = KNOWLEDGE / f"{category}.md"

        if not file.exists():

            return ""

        return file.read_text(
            encoding="utf-8"
        )