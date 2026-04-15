"""IMAP IDLE watcher for push notifications on new mail.

RFC 2177 IDLE extension allows a client to receive notifications
when new mail arrives, instead of polling.
"""

import asyncio
import imaplib
import logging
import select
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Dict, List, Optional, Set

from ..credentials import Credentials

logger = logging.getLogger(__name__)


@dataclass
class IdleConfig:
    """Configuration for an IDLE connection."""

    account_id: str
    email: str
    host: str
    port: int
    credential_file: str
    use_ssl: bool = True
    folder: str = "INBOX"


class IMAPIdleConnection:
    """Manages a single IMAP IDLE connection for one account."""

    # IDLE timeout in seconds (RFC recommends no more than 29 minutes)
    # We use 28 minutes to be safe
    IDLE_TIMEOUT = 28 * 60

    # Reconnect delay in seconds after disconnection
    RECONNECT_DELAY = 30

    def __init__(
        self,
        config: IdleConfig,
        on_new_mail: Callable[[str], None],
    ):
        """Initialize IDLE connection.

        Args:
            config: IDLE configuration
            on_new_mail: Callback when new mail arrives (receives account_id)
        """
        self.config = config
        self.on_new_mail = on_new_mail
        self._connection: Optional[imaplib.IMAP4_SSL] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._idle_tag: Optional[bytes] = None

    def _connect(self) -> bool:
        """Establish IMAP connection and enter IDLE mode.

        Returns:
            True if connection successful, False otherwise
        """
        try:
            logger.info(f"Connecting IMAP IDLE for {self.config.account_id}")

            # Load password
            password = Credentials.load_password(self.config.credential_file)

            # Connect (timeout prevents indefinite hang on flaky servers)
            if self.config.use_ssl:
                self._connection = imaplib.IMAP4_SSL(
                    self.config.host, self.config.port, timeout=30
                )
            else:
                self._connection = imaplib.IMAP4(
                    self.config.host, self.config.port, timeout=30
                )

            # Login
            self._connection.login(self.config.email, password)

            # Select folder
            typ, data = self._connection.select(self.config.folder)
            if typ != "OK":
                logger.error(f"Failed to select {self.config.folder}")
                return False

            # Check IDLE capability
            typ, capabilities = self._connection.capability()
            if typ == "OK":
                cap_str = capabilities[0].decode("utf-8", errors="ignore")
                if "IDLE" not in cap_str:
                    logger.warning(
                        f"IMAP server for {self.config.account_id} doesn't support IDLE"
                    )
                    return False

            logger.info(
                f"IMAP IDLE connected for {self.config.account_id} "
                f"(folder: {self.config.folder})"
            )
            return True

        except Exception as e:
            logger.error(f"IMAP IDLE connection failed for {self.config.account_id}: {e}")
            self._connection = None
            return False

    def _enter_idle(self) -> bool:
        """Send IDLE command to server.

        Returns:
            True if successful, False otherwise
        """
        if not self._connection:
            return False

        try:
            # Send IDLE command
            self._idle_tag = self._connection._new_tag()
            self._connection.send(self._idle_tag + b" IDLE\r\n")

            # Wait for continuation response (+)
            # May need to skip OK response from previous IDLE if timing is off
            for _ in range(3):  # Try up to 3 reads
                response = self._connection.readline()
                if response.startswith(b"+"):
                    logger.debug(f"Entered IDLE mode for {self.config.account_id}")
                    return True
                elif b"OK" in response and b"Idle" in response:
                    # This is the OK from previous IDLE session, skip it
                    logger.debug(f"Skipping previous IDLE OK response: {response}")
                    continue
                elif response.startswith(b"*"):
                    # Unilateral response (EXISTS, EXPUNGE, etc.) - skip
                    logger.debug(f"Skipping unilateral response: {response}")
                    continue
                else:
                    logger.error(f"IDLE command failed: {response}")
                    return False

            logger.error(f"Failed to enter IDLE after retries for {self.config.account_id}")
            return False

        except Exception as e:
            logger.error(f"Failed to enter IDLE for {self.config.account_id}: {e}")
            return False

    def _exit_idle(self) -> bool:
        """Send DONE to exit IDLE mode.

        Returns:
            True if successful, False otherwise
        """
        if not self._connection:
            return False

        try:
            # Send DONE to exit IDLE
            self._connection.send(b"DONE\r\n")

            # Read response (should be OK)
            response = self._connection.readline()
            logger.debug(f"IDLE exit response for {self.config.account_id}: {response}")

            self._idle_tag = None
            return True

        except Exception as e:
            logger.error(f"Failed to exit IDLE for {self.config.account_id}: {e}")
            return False

    def _watch_loop(self):
        """Main IDLE watching loop (runs in separate thread)."""
        while self._running and not self._stop_event.is_set():
            # Try to connect
            if not self._connect():
                logger.warning(
                    f"IDLE connection failed for {self.config.account_id}, "
                    f"retrying in {self.RECONNECT_DELAY}s"
                )
                self._stop_event.wait(self.RECONNECT_DELAY)
                continue

            # Main IDLE loop
            idle_start = time.time()
            while self._running and not self._stop_event.is_set():
                # Enter IDLE mode
                if not self._enter_idle():
                    break

                try:
                    # Wait for server response using select with timeout
                    # Use shorter timeout for responsiveness to stop_event
                    sock = self._connection.socket()
                    readable, _, _ = select.select([sock], [], [], 30)

                    if readable:
                        # Read response from server
                        response = self._connection.readline()
                        logger.debug(
                            f"IDLE response for {self.config.account_id}: {response}"
                        )

                        # Check for EXISTS (new mail)
                        if b"EXISTS" in response:
                            logger.info(
                                f"New mail detected for {self.config.account_id}"
                            )
                            # Exit IDLE before callback
                            self._exit_idle()
                            # Notify callback
                            try:
                                self.on_new_mail(self.config.account_id)
                            except Exception as e:
                                logger.error(f"Callback error: {e}")
                            # Re-enter IDLE loop
                            idle_start = time.time()
                            continue

                        # Check for EXPUNGE (message deleted)
                        if b"EXPUNGE" in response:
                            logger.debug(f"Message expunged for {self.config.account_id}")
                            # Exit IDLE and continue
                            self._exit_idle()
                            idle_start = time.time()
                            continue

                    # Exit IDLE periodically to refresh (per RFC recommendation)
                    if time.time() - idle_start > self.IDLE_TIMEOUT:
                        logger.debug(
                            f"IDLE timeout refresh for {self.config.account_id}"
                        )
                        self._exit_idle()
                        idle_start = time.time()
                        # NOOP to keep connection alive
                        self._connection.noop()
                    else:
                        # No data, exit IDLE and re-enter
                        self._exit_idle()

                except (OSError, ConnectionError, imaplib.IMAP4.error) as e:
                    logger.warning(f"IDLE connection error: {e}")
                    break
                except Exception as e:
                    logger.error(f"Unexpected IDLE error: {e}")
                    break

            # Cleanup connection
            if self._connection:
                try:
                    self._connection.logout()
                except Exception:
                    pass
                self._connection = None

            # Wait before reconnecting (if still running)
            if self._running and not self._stop_event.is_set():
                logger.info(
                    f"IDLE disconnected for {self.config.account_id}, "
                    f"reconnecting in {self.RECONNECT_DELAY}s"
                )
                self._stop_event.wait(self.RECONNECT_DELAY)

    def start(self):
        """Start the IDLE watcher thread."""
        if self._running:
            return

        self._running = True
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._watch_loop,
            name=f"imap-idle-{self.config.account_id}",
            daemon=True,
        )
        self._thread.start()
        logger.info(f"Started IMAP IDLE watcher for {self.config.account_id}")

    def stop(self):
        """Stop the IDLE watcher thread."""
        if not self._running:
            return

        self._running = False
        self._stop_event.set()

        # Try to wake up the select by closing socket
        if self._connection:
            try:
                # Exit IDLE first if in IDLE mode
                if self._idle_tag:
                    self._exit_idle()
                self._connection.logout()
            except Exception:
                pass
            self._connection = None

        # Wait for thread to finish
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None

        logger.info(f"Stopped IMAP IDLE watcher for {self.config.account_id}")


class IMAPIdleWatcher:
    """Manages IDLE connections for multiple accounts."""

    def __init__(self, on_new_mail: Optional[Callable[[str], None]] = None):
        """Initialize the IDLE watcher.

        Args:
            on_new_mail: Default callback when new mail arrives (receives account_id).
                        Can be overridden per-account.
        """
        self._connections: Dict[str, IMAPIdleConnection] = {}
        self._default_callback = on_new_mail or self._default_on_new_mail
        self._enabled = True

    def _default_on_new_mail(self, account_id: str):
        """Default callback when no callback provided."""
        logger.info(f"New mail for {account_id} (no callback configured)")

    def add_account(
        self,
        config: IdleConfig,
        on_new_mail: Optional[Callable[[str], None]] = None,
    ):
        """Add an account to watch.

        Args:
            config: IDLE configuration for the account
            on_new_mail: Optional custom callback for this account
        """
        if config.account_id in self._connections:
            logger.warning(f"Account {config.account_id} already being watched")
            return

        callback = on_new_mail or self._default_callback
        connection = IMAPIdleConnection(config, callback)
        self._connections[config.account_id] = connection

        if self._enabled:
            connection.start()

        logger.info(f"Added IDLE watcher for account {config.account_id}")

    def remove_account(self, account_id: str):
        """Remove an account from watching.

        Args:
            account_id: Account ID to remove
        """
        if account_id not in self._connections:
            return

        connection = self._connections.pop(account_id)
        connection.stop()
        logger.info(f"Removed IDLE watcher for account {account_id}")

    def start_all(self):
        """Start watching all accounts."""
        self._enabled = True
        for account_id, connection in self._connections.items():
            try:
                connection.start()
            except Exception as e:
                logger.error(f"Failed to start IDLE for {account_id}: {e}")

    def stop_all(self):
        """Stop watching all accounts."""
        self._enabled = False
        for account_id, connection in self._connections.items():
            try:
                connection.stop()
            except Exception as e:
                logger.error(f"Failed to stop IDLE for {account_id}: {e}")

    def get_watched_accounts(self) -> List[str]:
        """Get list of accounts being watched.

        Returns:
            List of account IDs
        """
        return list(self._connections.keys())

    def is_watching(self, account_id: str) -> bool:
        """Check if an account is being watched.

        Args:
            account_id: Account ID to check

        Returns:
            True if account is being watched
        """
        return account_id in self._connections


# Global IDLE watcher instance
_idle_watcher: Optional[IMAPIdleWatcher] = None


def get_idle_watcher() -> IMAPIdleWatcher:
    """Get the global IDLE watcher instance."""
    global _idle_watcher
    if _idle_watcher is None:
        _idle_watcher = IMAPIdleWatcher()
    return _idle_watcher


def shutdown_idle_watcher():
    """Shutdown the global IDLE watcher."""
    global _idle_watcher
    if _idle_watcher:
        _idle_watcher.stop_all()
        _idle_watcher = None
