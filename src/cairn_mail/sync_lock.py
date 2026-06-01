"""Advisory file lock shared by the incremental and deep sync paths.

Two sync processes hitting the same DB and the same IMAP connection pool at
once corrupts transactional sync state — the empty-sync counter, the pending
queue, and the provider connections all assume a single writer. This module
provides a non-blocking advisory lock so the second entrant bows out cleanly
instead of racing.

The lock lives next to the database it protects (`<db_dir>/sync.lock`). That
gives one stable path regardless of how sync was invoked — the systemd timer
and a manual `cairn-mail sync deep` resolve to the same file, which a
`/run/cairn-mail` RuntimeDirectory does NOT (it only exists while a unit is
mid-run, so manual runs and systemd runs end up on different inodes and never
exclude each other). An `fcntl` advisory lock is released by the kernel when
the holding process exits, so a crash never wedges the next run, and a stale
lock file on disk is harmless because the lock lives on the open fd, not on
the file's existence.
"""

import errno
import fcntl
import logging
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Optional, Union

logger = logging.getLogger(__name__)

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


def _read_holder_pid(path: Path) -> Optional[int]:
    try:
        return int(path.read_text().strip())
    except (OSError, ValueError):
        return None


@contextmanager
def sync_lock(db_path: Union[str, Path]):
    """Acquire the advisory sync lock for the database at `db_path`.

    The lock file sits beside the DB so every entrant — systemd timer or
    manual CLI — contends on the same path. A custom `--db` gets its own
    lock, which is correct: a different DB is not a conflicting writer.

    Raises:
        SyncLockHeld: if another process already holds the lock. The caller
            is expected to log and exit cleanly rather than wait.
    """
    lock_path = Path(db_path).parent / _LOCK_FILENAME
    lock_path.parent.mkdir(parents=True, exist_ok=True)

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
