from brain.providers.provider_manager import ProviderManager
from brain.models import Conversation
from brain.models import Message
from brain.models import Role

manager = ProviderManager()

conversation = Conversation()

conversation.add(

    Message(

        role=Role.USER,

        content="Reply with exactly one word."

    )

)

response = manager.chat(

    conversation

)

print()

print(response.provider)

print(response.text)