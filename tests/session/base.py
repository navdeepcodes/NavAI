from brain.session.session import Session
from brain.session.conversation_resolver import ConversationResolver


class SessionTester:

    def __init__(self):

        self.session = Session()

        self.resolver = ConversationResolver()

    def user(
        self,
        text: str,
    ):

        self.session.add_user(text)

    def mike(
        self,
        text: str,
    ):

        self.session.add_assistant(text)

    def resolve(
        self,
        text: str,
    ):

        return self.resolver.resolve(
            session=self.session,
            message=text,
        )