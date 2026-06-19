"""Out-of-band double-Esc kill switch: detect the panic gesture and stop the running turn.

Layers: ``channel`` (cross-process stop file), ``gesture`` (tap math), ``listener`` (per-platform
global Esc listeners), ``macos_tap`` (the self-healing Quartz tap), ``autostart`` (the OS-launched
``holo guard`` service). Process force-kill lives in ``agent_client.launcher`` and the turn-level
stop poll in ``agent_client.session_runner``, since both are intrinsic to those subsystems.
"""

from __future__ import annotations

from holo_desktop.killswitch.autostart import AutostartResult, ensure_autostart, ensure_loaded
from holo_desktop.killswitch.channel import StopSentinel, request_stop
from holo_desktop.killswitch.listener import (
    KILL_SWITCH_ARMED_HINT,
    KILL_SWITCH_UNAVAILABLE_HINT,
    ArmOutcome,
    StopListener,
    arm_stop_listener,
    is_interactive_tty,
)

__all__ = [
    "KILL_SWITCH_ARMED_HINT",
    "KILL_SWITCH_UNAVAILABLE_HINT",
    "ArmOutcome",
    "AutostartResult",
    "StopListener",
    "StopSentinel",
    "arm_stop_listener",
    "ensure_autostart",
    "ensure_loaded",
    "is_interactive_tty",
    "request_stop",
]
