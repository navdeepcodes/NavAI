from memory.session import SessionMemory
from memory.longterm import LongTermMemory
from memory.analyzer import MemoryAnalyzer
from memory.retriever import MemoryRetriever
from memory.search import MemorySearch


class MemoryManager:

    def __init__(self):

        self.session = SessionMemory()

        self.longterm = LongTermMemory()

        self.analyzer = MemoryAnalyzer()

        self.retriever = MemoryRetriever()

        self.search = MemorySearch()

    # -----------------------------------------
    # Store Memory
    # -----------------------------------------

    def remember(
        self,
        role: str,
        message: str
    ):

        # Always save to session
        self.session.add(
            role,
            message
        )

        # Only analyze user messages
        memory = self.analyzer.analyze(
            role,
            message
        )

        if memory is None:

            return

        self.longterm.save(

            memory.category,

            memory.content

        )

    # -----------------------------------------
    # Conversation History
    # -----------------------------------------

    def conversation(
        self,
        limit=50
    ):

        return self.session.last(limit)

    # -----------------------------------------
    # All Long-Term Memory
    # -----------------------------------------

    def context(self):

        return self.retriever.retrieve()

    # -----------------------------------------
    # Relevant Memory Search
    # -----------------------------------------

    def relevant_memory(
        self,
        query: str
    ):

        results = self.search.search(query)

        if not results:

            return ""

        output = []

        for _, category, line in results:

            output.append(

                f"[{category.upper()}]\n{line}"

            )

        return "\n\n".join(output)

    # -----------------------------------------
    # Recall Category
    # -----------------------------------------

    def recall(
        self,
        category
    ):

        return self.retriever.retrieve_category(
            category
        )

    # -----------------------------------------
    # Clear Session
    # -----------------------------------------

    def clear_session(self):

        self.session.clear()