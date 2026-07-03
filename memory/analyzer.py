from memory.models import Memory


class MemoryAnalyzer:

    def analyze(
        self,
        role: str,
        message: str,
    ):

        if role != "user":
            return None

        text = message.lower().strip()

        if len(text) < 8:
            return None

        ignored = {
            "hi",
            "hello",
            "hey",
            "thanks",
            "thank you",
            "ok",
            "okay",
            "cool",
            "nice",
            "bye",
            "lol",
            "haha"
        }

        if text in ignored:
            return None

        categories = {

            "profile": [
                "i am",
                "i'm",
                "my name",
                "my age",
                "i study",
                "i work",
                "i live"
            ],

            "preferences": [
                "i like",
                "i love",
                "i prefer",
                "favorite",
                "favourite",
                "always use",
                "usually use"
            ],

            "projects": [
                "project",
                "building",
                "working on",
                "developing",
                "creating",
                "website",
                "app",
                "software",
                "assistant",
                "mike",
                "navai",
                "bhooswarga"
            ],

            "goals": [
                "my goal",
                "i want",
                "i plan",
                "i will",
                "aim"
            ],

            "education": [
                "college",
                "university",
                "engineering",
                "semester",
                "cgpa"
            ],

            "skills": [
                "python",
                "react",
                "nextjs",
                "flutter",
                "typescript",
                "javascript"
            ]

        }

        for category, keywords in categories.items():

            if any(k in text for k in keywords):

                return Memory(

                    category=category,

                    content=message,

                    importance=8

                )

        return None