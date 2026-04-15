"""Provider factory for creating provider instances from database accounts."""

import logging
from typing import TYPE_CHECKING

from .base import BaseEmailProvider
from .implementations.gmail import GmailConfig, GmailProvider
from .registry import ProviderRegistry

if TYPE_CHECKING:
    from ..db.models import Account

logger = logging.getLogger(__name__)


class ProviderFactory:
    """Factory for creating provider instances from database accounts."""

    @staticmethod
    def create_from_account(account: "Account") -> BaseEmailProvider:
        """
        Create appropriate provider from database account.

        Args:
            account: Database Account record with provider and settings

        Returns:
            Configured provider instance

        Raises:
            ValueError: If provider type is not supported
        """
        if account.provider == "gmail":
            config = GmailConfig(
                account_id=account.id,
                email=account.email,
                credential_file=account.settings.get("credential_file", ""),
                label_prefix=account.settings.get("label_prefix", "AI"),
                label_colors=account.settings.get("label_colors", {}),
            )
            logger.debug(f"Creating Gmail provider for {account.email}")
            return ProviderRegistry.get_provider("gmail", config)

        elif account.provider == "imap":
            # Import dynamically to avoid circular imports
            from .implementations.imap import IMAPConfig

            config = IMAPConfig(
                account_id=account.id,
                email=account.email,
                credential_file=account.settings.get("credential_file", ""),
                host=account.settings["imap_host"],
                port=account.settings.get("imap_port", 993),
                use_ssl=account.settings.get("imap_tls", True),
                folder=account.settings.get("imap_folder", "INBOX"),
                # SMTP settings for sending
                smtp_host=account.settings.get("smtp_host"),
                smtp_port=account.settings.get("smtp_port", 587),
                smtp_tls=account.settings.get("smtp_tls", True),
                smtp_password_file=account.settings.get("smtp_password_file"),
            )
            logger.debug(f"Creating IMAP provider for {account.email}")
            return ProviderRegistry.get_provider("imap", config)

        else:
            raise ValueError(f"Unsupported provider: {account.provider}")
