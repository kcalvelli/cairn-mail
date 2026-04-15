"""IMAP server auto-detection registry."""

from typing import Dict, Tuple


class IMAPServerRegistry:
    """Registry of known IMAP server configurations for auto-detection."""

    # Format: domain -> (host, port, use_ssl)
    KNOWN_SERVERS: Dict[str, Tuple[str, int, bool]] = {
        # Gmail
        "gmail.com": ("imap.gmail.com", 993, True),
        "googlemail.com": ("imap.gmail.com", 993, True),
        # Fastmail
        "fastmail.com": ("imap.fastmail.com", 993, True),
        "fastmail.fm": ("imap.fastmail.com", 993, True),
        # ProtonMail (requires ProtonMail Bridge running locally)
        "protonmail.com": ("127.0.0.1", 1143, False),
        "proton.me": ("127.0.0.1", 1143, False),
        "pm.me": ("127.0.0.1", 1143, False),
        # iCloud
        "icloud.com": ("imap.mail.me.com", 993, True),
        "me.com": ("imap.mail.me.com", 993, True),
        # Outlook/Hotmail
        "outlook.com": ("outlook.office365.com", 993, True),
        "hotmail.com": ("outlook.office365.com", 993, True),
        "live.com": ("outlook.office365.com", 993, True),
        # Yahoo
        "yahoo.com": ("imap.mail.yahoo.com", 993, True),
        "ymail.com": ("imap.mail.yahoo.com", 993, True),
        # AOL
        "aol.com": ("imap.aol.com", 993, True),
        # Zoho
        "zoho.com": ("imap.zoho.com", 993, True),
        "zohomail.com": ("imap.zoho.com", 993, True),
        # GMX
        "gmx.com": ("imap.gmx.com", 993, True),
        "gmx.net": ("imap.gmx.com", 993, True),
        # Mail.com
        "mail.com": ("imap.mail.com", 993, True),
        # Tutanota (does not support IMAP - included for error messaging)
        "tutanota.com": (None, None, None),
        "tuta.io": (None, None, None),
    }

    @classmethod
    def get_server_config(
        cls, email: str
    ) -> Tuple[str, int, bool]:
        """
        Get IMAP server configuration for an email address.

        Args:
            email: Email address (e.g., "user@fastmail.com")

        Returns:
            Tuple of (host, port, use_ssl)

        Raises:
            ValueError: If provider doesn't support IMAP
        """
        domain = email.split("@")[-1].lower()

        if domain in cls.KNOWN_SERVERS:
            server_config = cls.KNOWN_SERVERS[domain]

            # Check for providers that don't support IMAP
            if server_config[0] is None:
                raise ValueError(
                    f"{domain} does not support IMAP. "
                    f"Use their web interface or native app instead."
                )

            return server_config

        # Default: Try imap.{domain}
        return (f"imap.{domain}", 993, True)

    @classmethod
    def get_host(cls, domain: str) -> str:
        """
        Get IMAP host for a domain (legacy method for compatibility).

        Args:
            domain: Email domain (e.g., "fastmail.com")

        Returns:
            IMAP hostname
        """
        if domain in cls.KNOWN_SERVERS:
            server_config = cls.KNOWN_SERVERS[domain]
            if server_config[0] is None:
                return f"imap.{domain}"  # Fallback for unsupported providers
            return server_config[0]

        return f"imap.{domain}"

    @classmethod
    def is_known_provider(cls, domain: str) -> bool:
        """
        Check if a domain is a known provider.

        Args:
            domain: Email domain

        Returns:
            True if provider is in registry
        """
        return domain in cls.KNOWN_SERVERS

    @classmethod
    def supports_imap(cls, domain: str) -> bool:
        """
        Check if a provider supports IMAP.

        Args:
            domain: Email domain

        Returns:
            True if provider supports IMAP
        """
        if domain not in cls.KNOWN_SERVERS:
            return True  # Assume unknown providers support IMAP

        server_config = cls.KNOWN_SERVERS[domain]
        return server_config[0] is not None
