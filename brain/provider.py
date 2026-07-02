from brain.conversation import Conversation


class Brain:

    def __init__(self):

        self.conversation = Conversation()

    def ask(self, message):

        return self.conversation.send(message)