"""Cross-process stop channel: a turn honors only stop requests filed after it began."""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

STOP_PATH = Path.home() / ".holo" / "stop"


def request_stop(now: float) -> None:
    """Record a stop request at wall-clock ``now`` for any in-flight turn to observe.

    Args:
        now: Wall-clock epoch seconds of the request (``time.time()`` at the call site).
    """
    STOP_PATH.parent.mkdir(parents=True, exist_ok=True)
    STOP_PATH.write_text(str(now), encoding="utf-8")


class StopSentinel:
    """Reads the shared stop file, reporting a request only when filed after ``started_at``."""

    def __init__(self, started_at: float) -> None:
        """Bind to the turn's start time.

        Args:
            started_at: Wall-clock epoch seconds when this turn began; older requests are stale.
        """
        self._started_at = started_at

    def stop_requested(self) -> bool:
        """True when a stop was filed after this turn began.

        Total by design: a missing, partial, or unreadable channel reads as "no stop" so the poll that
        drives the kill switch can never crash on a transient read error (and so be mistaken for a stop).
        """
        try:
            raw = STOP_PATH.read_text(encoding="utf-8")
        except FileNotFoundError:
            return False
        except OSError:
            logger.debug("could not read the stop channel %s", STOP_PATH, exc_info=True)
            return False
        try:
            requested_at = float(raw)
        except ValueError:
            return False
        return requested_at > self._started_at
