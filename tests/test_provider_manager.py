from brain.providers.provider_manager import ProviderManager

from brain.providers.task_type import TaskType


manager = ProviderManager()

print()

print("=" * 60)

print("AVAILABLE PROVIDERS")

print("=" * 60)

for provider in manager.provider_names():

    print(provider)

print()

print("=" * 60)

print("CHAT")

print("=" * 60)

provider = manager.best_for(

    TaskType.CHAT

)

print(

    provider.name

)

print()

print("=" * 60)

print("VISION")

print("=" * 60)

provider = manager.best_for(

    TaskType.VISION,

    requires_vision=True

)

print(

    provider.name

)

print()

print("=" * 60)

print("REASONING")

print("=" * 60)

provider = manager.best_for(

    TaskType.REASONING

)

print(

    provider.name

)

print()

print("=" * 60)

print("CODING")

print("=" * 60)

provider = manager.best_for(

    TaskType.CODING

)

print(

    provider.name

)