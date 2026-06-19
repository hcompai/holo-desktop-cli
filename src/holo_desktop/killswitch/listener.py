"""Global Esc-tap listener that files a kill-switch stop request; the backend is chosen per platform."""

from __future__ import annotations

import logging
import platform
import sys
import time
from enum import Enum
from typing import Protocol

from holo_desktop.killswitch.gesture import STOP_KEY_TAPS, STOP_KEY_WINDOW_S, StopKeySwitch

logger = logging.getLogger(__name__)

# Single source of truth for the user-facing arming copy; surfaces render it in their own style.
KILL_SWITCH_ARMED_HINT = "kill switch armed — press Esc twice fast to stop"
KILL_SWITCH_UNAVAILABLE_HINT = (
    "kill switch unavailable — double-Esc won't stop this run; grant Input Monitoring "
    "(System Settings → Privacy & Security), or use holo stop"
)


class ArmOutcome(Enum):
    """Result of an arming attempt; the caller picks the message and rendering."""

    DISABLED = "disabled"
    ARMED = "armed"
    UNAVAILABLE = "unavailable"


def is_interactive_tty() -> bool:
    """True only with a real terminal on both ends; the sole gate for arming the global listener."""
    return sys.stdin.isatty() and sys.stdout.isatty()


def arm_stop_listener(*, enabled: bool) -> tuple[StopListener | None, ArmOutcome]:
    """Arm the double-Esc kill switch; the outcome tells the caller which hint to surface."""
    if not enabled:
        return None, ArmOutcome.DISABLED
    listener = StopListener()
    if not listener.start():
        return None, ArmOutcome.UNAVAILABLE
    return listener, ArmOutcome.ARMED


class KillSwitchBackend(Protocol):
    """A platform listener that arms a global Esc gesture and stops cleanly."""

    def start(self) -> bool: ...

    def stop(self) -> None: ...


class StopListener:
    """Arms a global Esc kill switch via the platform backend, firing on a rapid Esc gesture."""

    def __init__(self) -> None:
        self._switch = StopKeySwitch(STOP_KEY_TAPS, STOP_KEY_WINDOW_S)
        self._backend = build_backend(self._switch)

    def start(self) -> bool:
        """Start listening; False if the backend is missing or lacks permission."""
        return self._backend.start()

    def stop(self) -> None:
        """Stop the listener if running."""
        self._backend.stop()


def build_backend(switch: StopKeySwitch) -> KillSwitchBackend:
    """The macOS self-healing tap on darwin; the pynput listener elsewhere."""
    if platform.system() == "Darwin":
        from holo_desktop.killswitch.macos_tap import QuartzEscTap

        return QuartzEscTap(switch)
    return PynputEscListener(switch)


class _PynputListener(Protocol):
    """The slice of ``pynput.keyboard.Listener`` this module drives."""

    def start(self) -> None: ...

    def stop(self) -> None: ...


class PynputEscListener:
    """pynput global keyboard listener for non-macOS platforms."""

    def __init__(self, switch: StopKeySwitch) -> None:
        self._switch = switch
        self._listener: _PynputListener | None = None

    def start(self) -> bool:
        try:
            from pynput import keyboard
        except Exception:
            logger.warning("pynput is unavailable; the Esc kill switch is disabled")
            return False

        stop_key = keyboard.Key.esc

        def on_press(key: object) -> None:
            try:
                if self._switch.on_press(key == stop_key, time.monotonic()):
                    logger.warning("kill switch: Esc stop gesture detected; requesting stop")
            except Exception:
                logger.warning("kill-switch key handler failed", exc_info=True)

        try:
            listener = keyboard.Listener(on_press=on_press)
            listener.start()
        except Exception:
            logger.warning("could not start the keyboard listener (grant Input Monitoring?)", exc_info=True)
            return False
        self._listener = listener
        return True

    def stop(self) -> None:
        listener = self._listener
        if listener is not None:
            listener.stop()
            self._listener = None
