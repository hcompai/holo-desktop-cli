"""Machine-wide advisory lock: at most one desktop turn runs at a time across all holo processes."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import sys
from collections.abc import AsyncIterator
from pathlib import Path

logger = logging.getLogger(__name__)

LOCK_PATH = Path.home() / ".holo" / "desktop.lock"
# Poll cadence while another process or turn holds the lock; keeps the wait cancellable on Ctrl+C.
_POLL_S = 0.25

if sys.platform == "win32":
    import msvcrt

    def _try_acquire(fd: int) -> bool:
        try:
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            return True
        except OSError:
            return False

    def _release(fd: int) -> None:
        with contextlib.suppress(OSError):
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
else:
    import fcntl

    def _try_acquire(fd: int) -> bool:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:
            return False

    def _release(fd: int) -> None:
        with contextlib.suppress(OSError):
            fcntl.flock(fd, fcntl.LOCK_UN)


@contextlib.asynccontextmanager
async def desktop_turn() -> AsyncIterator[None]:
    """Hold the machine-wide desktop lock for one turn, polling until it is free.

    Not reentrant: each ``desktop_turn`` opens its own fd and the lock contends across fds even in
    one process, so a second ``desktop_turn`` entered while the first is held waits forever. One turn
    driver owns the lock at a time.
    """
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(LOCK_PATH, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        waited = False
        while not _try_acquire(fd):
            if not waited:
                logger.info("another desktop turn is in progress; waiting for the machine-wide lock")
                waited = True
            await asyncio.sleep(_POLL_S)
        try:
            yield
        finally:
            _release(fd)
    finally:
        os.close(fd)
