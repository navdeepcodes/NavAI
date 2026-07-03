from brain.providers.provider_manager import (
    ProviderManager
)


_manager = ProviderManager()


def get_provider():

    return _manager.get()