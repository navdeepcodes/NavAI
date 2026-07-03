from brain.providers.provider_manager import ProviderManager


_manager = ProviderManager()


def get_provider():

    """
    Returns the best provider for lightweight text tasks.
    Used by IntentEngine and other internal services.
    """

    return _manager.best_for_text()