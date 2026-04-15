"""Provider registry for dynamic loading."""

import logging
from typing import Dict, Type

from .base import BaseEmailProvider, ProviderConfig

logger = logging.getLogger(__name__)


class ProviderRegistry:
    """Registry for email provider implementations."""

    _providers: Dict[str, Type[BaseEmailProvider]] = {}

    @classmethod
    def register(cls, provider_type: str, provider_class: Type[BaseEmailProvider]) -> None:
        """Register a provider implementation.

        Args:
            provider_type: Provider type identifier (e.g., "gmail", "imap", "outlook")
            provider_class: Provider class to register
        """
        cls._providers[provider_type] = provider_class
        logger.debug(f"Registered provider: {provider_type} -> {provider_class.__name__}")

    @classmethod
    def get_provider(cls, provider_type: str, config: ProviderConfig) -> BaseEmailProvider:
        """Get a provider instance by type.

        Args:
            provider_type: Provider type identifier
            config: Provider configuration

        Returns:
            Instantiated provider

        Raises:
            ValueError: If provider type is not registered
        """
        if provider_type not in cls._providers:
            available = ", ".join(cls._providers.keys())
            raise ValueError(
                f"Unknown provider type: {provider_type}. Available: {available}"
            )

        provider_class = cls._providers[provider_type]
        return provider_class(config)

    @classmethod
    def list_providers(cls) -> Dict[str, Type[BaseEmailProvider]]:
        """List all registered providers.

        Returns:
            Dict mapping provider type to provider class
        """
        return cls._providers.copy()
