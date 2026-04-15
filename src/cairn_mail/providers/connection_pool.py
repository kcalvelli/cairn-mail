"""IMAP Connection Pool for persistent connections.

Maintains persistent IMAP connections to avoid re-authentication overhead
on each sync cycle. Connections are reused across sync cycles and automatically
cleaned up when idle.
"""

import asyncio
import imaplib
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, Optional, Callable, Any
from threading import Lock

logger = logging.getLogger(__name__)


@dataclass
class PooledConnection:
    """A pooled IMAP connection with metadata."""

    connection: imaplib.IMAP4_SSL
    account_id: str
    created_at: float = field(default_factory=time.time)
    last_used_at: float = field(default_factory=time.time)
    in_use: bool = False

    def is_healthy(self) -> bool:
        """Check if the connection is still usable."""
        try:
            # NOOP is a lightweight command to check connection health
            status, _ = self.connection.noop()
            return status == "OK"
        except Exception as e:
            logger.debug(f"Connection health check failed for {self.account_id}: {e}")
            return False

    def touch(self) -> None:
        """Update last_used_at timestamp."""
        self.last_used_at = time.time()


class IMAPConnectionPool:
    """Manages persistent IMAP connections per account.

    Features:
    - Connection reuse across sync cycles
    - Automatic health checks before reuse
    - Idle timeout cleanup
    - Thread-safe connection management

    Usage:
        pool = IMAPConnectionPool()

        # Get or create connection
        conn = pool.get_connection(
            account_id="my_account",
            create_fn=lambda: create_imap_connection(config)
        )

        # Use connection...

        # Release back to pool (keep alive)
        pool.release_connection("my_account")

        # Or close specific connection
        pool.close_connection("my_account")

        # Cleanup idle connections periodically
        pool.cleanup_idle_connections()

        # Close all on shutdown
        pool.close_all()
    """

    def __init__(
        self,
        max_idle_seconds: int = 300,
        health_check_on_acquire: bool = True,
    ):
        """Initialize the connection pool.

        Args:
            max_idle_seconds: Close connections idle longer than this (default 5 min)
            health_check_on_acquire: Check connection health before returning (default True)
        """
        self._connections: Dict[str, PooledConnection] = {}
        self._locks: Dict[str, Lock] = {}
        self._global_lock = Lock()
        self._max_idle_seconds = max_idle_seconds
        self._health_check_on_acquire = health_check_on_acquire

    def _get_lock(self, account_id: str) -> Lock:
        """Get or create a lock for an account."""
        with self._global_lock:
            if account_id not in self._locks:
                self._locks[account_id] = Lock()
            return self._locks[account_id]

    def get_connection(
        self,
        account_id: str,
        create_fn: Callable[[], imaplib.IMAP4_SSL],
    ) -> imaplib.IMAP4_SSL:
        """Get or create a connection for an account.

        Args:
            account_id: Unique identifier for the account
            create_fn: Function to create a new connection if needed

        Returns:
            IMAP connection (either existing or newly created)

        Raises:
            Exception: If connection creation fails
        """
        lock = self._get_lock(account_id)

        with lock:
            pooled = self._connections.get(account_id)

            # Check if we have a healthy existing connection
            if pooled is not None:
                if pooled.in_use:
                    logger.warning(
                        f"Connection for {account_id} already in use, creating new one"
                    )
                elif self._health_check_on_acquire and not pooled.is_healthy():
                    logger.info(f"Connection for {account_id} unhealthy, replacing")
                    self._close_connection_internal(pooled)
                    pooled = None
                else:
                    # Reuse existing connection
                    logger.debug(f"Reusing pooled connection for {account_id}")
                    pooled.in_use = True
                    pooled.touch()
                    return pooled.connection

            # Create new connection
            logger.info(f"Creating new pooled connection for {account_id}")
            try:
                connection = create_fn()
                pooled = PooledConnection(
                    connection=connection,
                    account_id=account_id,
                    in_use=True,
                )
                self._connections[account_id] = pooled
                return connection
            except Exception as e:
                logger.error(f"Failed to create connection for {account_id}: {e}")
                raise

    def release_connection(self, account_id: str) -> None:
        """Release a connection back to the pool (keep alive).

        Args:
            account_id: Account whose connection to release
        """
        lock = self._get_lock(account_id)

        with lock:
            pooled = self._connections.get(account_id)
            if pooled:
                pooled.in_use = False
                pooled.touch()
                logger.debug(f"Released connection for {account_id} back to pool")
            else:
                logger.warning(f"No connection to release for {account_id}")

    def close_connection(self, account_id: str) -> None:
        """Close and remove a specific connection.

        Args:
            account_id: Account whose connection to close
        """
        lock = self._get_lock(account_id)

        with lock:
            pooled = self._connections.pop(account_id, None)
            if pooled:
                self._close_connection_internal(pooled)
                logger.info(f"Closed connection for {account_id}")

    def _close_connection_internal(self, pooled: PooledConnection) -> None:
        """Close a connection (internal, no locking)."""
        try:
            pooled.connection.logout()
        except Exception as e:
            logger.debug(f"Error during logout for {pooled.account_id}: {e}")
        try:
            pooled.connection.close()
        except Exception:
            pass

    def cleanup_idle_connections(self) -> int:
        """Close connections that have been idle too long.

        Returns:
            Number of connections closed
        """
        now = time.time()
        closed = 0

        with self._global_lock:
            accounts_to_close = []
            for account_id, pooled in self._connections.items():
                if not pooled.in_use:
                    idle_time = now - pooled.last_used_at
                    if idle_time > self._max_idle_seconds:
                        accounts_to_close.append(account_id)

        for account_id in accounts_to_close:
            self.close_connection(account_id)
            closed += 1

        if closed > 0:
            logger.info(f"Cleaned up {closed} idle connection(s)")

        return closed

    def close_all(self) -> None:
        """Close all connections (for shutdown)."""
        with self._global_lock:
            account_ids = list(self._connections.keys())

        for account_id in account_ids:
            self.close_connection(account_id)

        logger.info(f"Closed all {len(account_ids)} connection(s)")

    def get_stats(self) -> Dict[str, Any]:
        """Get pool statistics.

        Returns:
            Dictionary with pool stats
        """
        with self._global_lock:
            total = len(self._connections)
            in_use = sum(1 for p in self._connections.values() if p.in_use)
            idle = total - in_use

            return {
                "total_connections": total,
                "in_use": in_use,
                "idle": idle,
                "accounts": list(self._connections.keys()),
            }

    def invalidate_folder_cache(self, account_id: str) -> None:
        """Invalidate folder cache for an account.

        Called when connection is reset and folders may have changed.

        Args:
            account_id: Account whose folder cache to invalidate
        """
        # This will be used by IMAPProvider to clear its folder mapping cache
        # when the connection pool detects a connection reset
        pass


# Global connection pool instance
_pool: Optional[IMAPConnectionPool] = None


def get_connection_pool() -> IMAPConnectionPool:
    """Get the global connection pool instance.

    Creates the pool on first access (lazy initialization).

    Returns:
        The global IMAPConnectionPool instance
    """
    global _pool
    if _pool is None:
        _pool = IMAPConnectionPool()
    return _pool


def shutdown_connection_pool() -> None:
    """Shutdown the global connection pool.

    Should be called during application shutdown.
    """
    global _pool
    if _pool is not None:
        _pool.close_all()
        _pool = None
