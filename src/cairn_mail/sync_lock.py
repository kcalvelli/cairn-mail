"""Advisory file lock shared by the incremental and deep sync paths.

Two sync processes hitting the same DB and the same IMAP connection pool at
once corrupts transactional sync state — the empty-sync counter, the pending
queue, and the provider connections all assume a single writer. This module
provides a non-blocking advisory lock so the second entrant bows out cleanly
instead of racing.

The lock lives on a tmpfs (`/run/cairn-mail/` under systemd, the user's
`$XDG_RUNTIME_DIR` otherwise). An `fcntl` advisory lock is released by the
kernel when the holding process exits, so a crash never wedges the next run.
"""

import errno
import fcntl
import logging
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_SYSTEM_LOCK_DIR = Path("/run/cairn-mail")
_LOCK_FILENAME = "sync.lock"


class SyncLockHeld(Exception):
    """Raised when the advisory sync lock is already held by another process.

    `holder_pid` is the PID recorded in the lock file, if it was readable.
    """

    def __init__(self, lock_path: Path, holder_pid: Optional[int] = None):
        self.lock_path = lock_path
        self.holder_pid = holder_pid
        held_by = f" (held by PID {holder_pid})" if holder_pid else ""
        super().__init__(f"sync lock {lock_path} is already held{held_by}")


def _resolve_lock_path() -> Path:
    """Pick the lock path: the systemd RuntimeDirectory if writable, else the
    user's XDG runtime dir (so a non-root manual invocation still locks)."""
    if os.access(_SYSTEM_LOCK_DIR, os.W_OK):
        return _SYSTEM_LOCK_DIR / _LOCK_FILENAME

    xdg = os.environ.get("XDG_RUNTIME_DIR")
    base = Path(xdg) / "cairn-mail" if xdg else Path.home() / ".cache/cairn-mail"
    base.mkdir(parents=True, exist_ok=True)
    return base / _LOCK_FILENAME


def _read_holder_pid(path: Path) -> Optional[int]:
    try:
        return int(path.read_text().strip())
    except (OSError, ValueError):
        return None


@contextmanager
def sync_lock():
    """Acquire the advisory sync lock for the duration of the context.

    Raises:
        SyncLockHeld: if another process already holds the lock. The caller
            is expected to log and exit cleanly rather than wait.
    """
    lock_path = _resolve_lock_path()
    # Open without truncating so a contended attempt can still read the
    # holder's PID.
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as e:
            if e.errno in (errno.EACCES, errno.EAGAIN):
                raise SyncLockHeld(lock_path, _read_holder_pid(lock_path)) from None
            raise

        # We hold it — stamp our PID for the next contender to read.
        os.ftruncate(fd, 0)
        os.write(fd, f"{os.getpid()}\n".encode())
        os.fsync(fd)
        logger.debug(f"Acquired sync lock {lock_path}")

        try:
            yield lock_path
        finally:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            except OSError:
                pass
            logger.debug(f"Released sync lock {lock_path}")
    finally:
        try:
            os.close(fd)
        except OSError:
            pass
