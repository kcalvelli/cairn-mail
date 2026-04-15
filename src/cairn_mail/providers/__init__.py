"""Email provider abstraction layer."""

from .base import EmailProvider, Message, Classification, ProviderConfig
from .registry import ProviderRegistry
from .implementations.gmail import GmailProvider
from .implementations.imap import IMAPProvider

# Register providers
ProviderRegistry.register("gmail", GmailProvider)
ProviderRegistry.register("imap", IMAPProvider)

__all__ = [
    "EmailProvider",
    "Message",
    "Classification",
    "ProviderConfig",
    "ProviderRegistry",
    "GmailProvider",
    "IMAPProvider",
]
