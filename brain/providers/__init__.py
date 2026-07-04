from __future__ import annotations

from .provider_manager import ProviderManager

manager = ProviderManager()

__all__ = (
    "manager",
    "ProviderManager",
)