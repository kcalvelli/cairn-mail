"""SMTP client wrapper for sending emails."""

import logging
import smtplib
import time
from dataclasses import dataclass
from email.message import EmailMessage
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class SMTPConfig:
    """SMTP server configuration."""

    host: str
    port: int = 587
    username: str = ""
    password: str = ""
    use_tls: bool = True
    timeout: int = 30


class SMTPClient:
    """SMTP client for sending emails with retry logic."""

    def __init__(self, config: SMTPConfig):
        """Initialize SMTP client.

        Args:
            config: SMTP configuration
        """
        self.config = config
        self._connection: Optional[smtplib.SMTP] = None

    def send_message(
        self,
        msg: EmailMessage,
        from_addr: str,
        to_addrs: List[str],
        max_retries: int = 3,
    ) -> str:
        """Send an email message via SMTP.

        Args:
            msg: MIME message to send
            from_addr: Sender email address
            to_addrs: List of recipient addresses (To + Cc + Bcc)
            max_retries: Maximum number of retry attempts

        Returns:
            Message ID from the sent message

        Raises:
            RuntimeError: If send fails after all retries
        """
        last_error = None

        for attempt in range(max_retries):
            try:
                # Connect and send
                self._connect()
                self._connection.send_message(msg, from_addr=from_addr, to_addrs=to_addrs)
                self._disconnect()

                # Extract Message-ID from sent message
                message_id = msg.get("Message-ID", "")
                logger.info(f"Message sent successfully: {message_id}")
                return message_id

            except (smtplib.SMTPException, OSError, TimeoutError) as e:
                last_error = e
                self._disconnect()  # Ensure clean state

                if attempt < max_retries - 1:
                    # Exponential backoff: 1s, 2s, 4s
                    wait_time = 2**attempt
                    logger.warning(f"Send attempt {attempt + 1}/{max_retries} failed: {e}. Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    logger.error(f"All {max_retries} send attempts failed: {e}")

        # All retries exhausted
        error_msg = f"Failed to send message after {max_retries} attempts: {last_error}"
        raise RuntimeError(error_msg)

    def _connect(self) -> None:
        """Establish SMTP connection and authenticate.

        Raises:
            RuntimeError: If connection or authentication fails
        """
        try:
            # Determine connection type based on port
            if self.config.port == 465 and self.config.use_tls:
                # Direct TLS connection (SMTPS)
                logger.debug(f"Connecting to {self.config.host}:{self.config.port} with direct TLS")
                self._connection = smtplib.SMTP_SSL(
                    self.config.host,
                    self.config.port,
                    timeout=self.config.timeout,
                )
            else:
                # Plain connection with optional STARTTLS
                logger.debug(f"Connecting to {self.config.host}:{self.config.port}")
                self._connection = smtplib.SMTP(
                    self.config.host,
                    self.config.port,
                    timeout=self.config.timeout,
                )

                if self.config.use_tls:
                    # Upgrade to TLS with STARTTLS
                    logger.debug("Upgrading connection with STARTTLS")
                    self._connection.starttls()
                else:
                    logger.warning("SMTP connection is not encrypted (TLS disabled)")

            # Authenticate if credentials provided
            if self.config.username and self.config.password:
                logger.debug(f"Authenticating as {self.config.username}")
                self._connection.login(self.config.username, self.config.password)
            else:
                logger.debug("No credentials provided, skipping authentication")

            logger.info(f"SMTP connection established to {self.config.host}:{self.config.port}")

        except smtplib.SMTPAuthenticationError as e:
            error_msg = f"SMTP authentication failed for {self.config.username}: {e}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)

        except (smtplib.SMTPException, OSError) as e:
            error_msg = f"SMTP connection failed to {self.config.host}:{self.config.port}: {e}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)

    def _disconnect(self) -> None:
        """Close SMTP connection."""
        if self._connection:
            try:
                self._connection.quit()
                logger.debug("SMTP connection closed")
            except smtplib.SMTPException:
                # Ignore errors during disconnect
                pass
            finally:
                self._connection = None

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self._disconnect()
