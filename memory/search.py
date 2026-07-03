from pathlib import Path


KNOWLEDGE = Path(__file__).parent / "knowledge"


class MemorySearch:

    def search(
        self,
        query: str,
        limit: int = 5
    ):

        query = query.lower()

        results = []

        for file in KNOWLEDGE.glob("*.md"):

            try:

                lines = file.read_text(
                    encoding="utf-8"
                ).splitlines()

                for line in lines:

                    score = 0

                    for word in query.split():

                        if word in line.lower():

                            score += 1

                    if score > 0:

                        results.append(

                            (

                                score,

                                file.stem,

                                line

                            )

                        )

            except Exception:

                pass

        results.sort(

            reverse=True,

            key=lambda x: x[0]

        )

        return results[:limit]