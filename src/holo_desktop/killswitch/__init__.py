"""Double-Esc kill switch: the SDK's global listener, with Holo's stop command in its hints."""

from __future__ import annotations

import sys

from hai_agents_local.killswitch import KILL_SWITCH_ARMED_HINT, KILL_SWITCH_UNAVAILABLE_HINT, arm_esc_listener

ARMED_HINT = KILL_SWITCH_ARMED_HINT
UNAVAILABLE_HINT = KILL_SWITCH_UNAVAILABLE_HINT.replace("`hai local stop`", "`holo stop`")
arm = arm_esc_listener


def is_interactive_tty() -> bool:
    """Only a real terminal has a human who can press Esc."""
    return sys.stdin.isatty() and sys.stderr.isatty()
