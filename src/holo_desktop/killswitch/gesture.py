"""The panic gesture: N rapid taps of the stop key, which files a stop request when completed."""

from __future__ import annotations

import time

from holo_desktop.killswitch.channel import request_stop

STOP_KEY_TAPS = 2
STOP_KEY_WINDOW_S = 0.6


class MultiTapDetector:
    """Fires once when ``taps`` timestamps fall within ``window_s`` of each other, then resets."""

    def __init__(self, taps: int, window_s: float) -> None:
        """Configure the gesture.

        Args:
            taps: Number of taps required to fire.
            window_s: Maximum span, in seconds, the qualifying taps may span.
        """
        if taps < 2:
            raise ValueError(f"taps must be at least 2, got {taps}")
        if window_s <= 0:
            raise ValueError(f"window_s must be positive, got {window_s}")
        self._taps = taps
        self._window_s = window_s
        self._times: list[float] = []

    def record(self, t: float) -> bool:
        """Record a tap at monotonic time ``t``; return True iff it completes the gesture."""
        self._times = [seen for seen in self._times if t - seen <= self._window_s]
        self._times.append(t)
        if len(self._times) >= self._taps:
            self._times.clear()
            return True
        return False


class StopKeySwitch:
    """Files a stop request when the stop key is tapped ``taps`` times within ``window_s``."""

    def __init__(self, taps: int, window_s: float) -> None:
        """Configure the gesture.

        Args:
            taps: Number of stop-key taps required to fire.
            window_s: Maximum span, in seconds, those taps may cover.
        """
        self._detector = MultiTapDetector(taps=taps, window_s=window_s)

    def on_press(self, is_stop_key: bool, now: float) -> bool:
        """Record a key press; on a completed gesture file a stop request and return True.

        Args:
            is_stop_key: Whether the pressed key is the stop key (Esc).
            now: Monotonic timestamp of the press, used for the tap window.
        """
        if not is_stop_key:
            return False
        if not self._detector.record(now):
            return False
        request_stop(time.time())
        return True
