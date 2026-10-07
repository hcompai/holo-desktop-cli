"""Double-Esc kill switch: the SDK's Quartz tap on macOS, a pynput listener on Windows; both file the SDK stop."""

from __future__ import annotations

import platform
import sys
import time
from typing import Protocol

from hai_agents_local.killswitch import MultiTapDetector, arm_esc_listener, request_stop

ARMED_HINT = "kill switch armed: press Esc twice fast to stop"
UNAVAILABLE_HINT = (
    "double-Esc kill switch unavailable; grant Input Monitoring to this terminal in "
    "System Settings → Privacy & Security, or stop with `holo stop`"
)


class Listener(Protocol):
    def stop(self) -> None: ...


def arm() -> Listener | None:
    """Arm the global double-Esc listener; None when unsupported here or not permitted."""
    # platform.system() not sys.platform: mypy narrows the latter and flags a branch unreachable per OS.
    system = platform.system()
    if system == "Darwin":
        return arm_esc_listener()
    if system == "Windows":
        return _arm_pynput()
    return None


def is_interactive_tty() -> bool:
    """Only a real terminal has a human who can press Esc."""
    return sys.stdin.isatty() and sys.stderr.isatty()


def _arm_pynput() -> Listener | None:
    from pynput import keyboard

    detector = MultiTapDetector()

    def on_press(key: object) -> None:
        if key == keyboard.Key.esc and detector.record(time.monotonic()):
            request_stop()

    listener = keyboard.Listener(on_press=on_press)
    listener.start()
    listener.wait()
    return listener if listener.running else None
