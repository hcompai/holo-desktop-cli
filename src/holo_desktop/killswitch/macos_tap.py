"""macOS Esc kill-switch tap that re-arms itself when the OS disables it.

Darwin-only: ``listener.build_backend`` selects this backend solely when ``platform.system() ==
"Darwin"`` and falls back to ``PynputEscListener`` everywhere else, so this module is never imported
off macOS. macOS earns the special-casing because global key monitoring is permissioned there (TCC /
Input Monitoring) and a ``kCGSessionEventTap`` is disabled by macOS when its callback exceeds the
watchdog budget (``kCGEventTapDisabledByTimeout``) or after a burst of user input
(``kCGEventTapDisabledByUserInput``). A heavy desktop turn floods the session with synthetic input
events, so the listen-only tap falls behind and gets disabled; re-enabling it in the callback keeps the
kill switch alive when it matters.

Testability: backend selection (``build_backend``) and the tap decision (``classify_tap_event``) are
Quartz-free and unit-tested; the live Input-Monitoring path needs a real grant and is verified manually.
"""

from __future__ import annotations

import enum
import logging
import threading
import time
from types import ModuleType
from typing import Protocol

logger = logging.getLogger(__name__)

# Carbon virtual key code for Esc; stable across keyboard layouts.
ESC_KEYCODE = 53
START_TIMEOUT_S = 2.0
STOP_JOIN_TIMEOUT_S = 2.0


class StopSwitch(Protocol):
    """The slice of the tap detector the tap drives."""

    def on_press(self, is_stop_key: bool, now: float) -> bool: ...


class EscTapDecision(enum.Enum):
    """What the tap callback should do with one delivered event."""

    REENABLE = "reenable"
    FORWARD_ESC = "forward_esc"
    IGNORE = "ignore"


def classify_tap_event(
    event_type: int,
    keycode: int,
    *,
    disabled_types: tuple[int, ...],
    keydown_type: int,
    esc_keycode: int,
) -> EscTapDecision:
    """Decide how to handle one tap event, with no dependency on Quartz so it is unit-testable."""
    if event_type in disabled_types:
        return EscTapDecision.REENABLE
    if event_type == keydown_type and keycode == esc_keycode:
        return EscTapDecision.FORWARD_ESC
    return EscTapDecision.IGNORE


class QuartzEscTap:
    """Owns a self-healing Quartz event tap that fires ``switch`` on each Esc keydown."""

    def __init__(self, switch: StopSwitch) -> None:
        self._switch = switch
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._armed = False
        self._quartz: ModuleType | None = None
        self._tap: object | None = None
        self._loop: object | None = None
        self._disabled_types: tuple[int, ...] = ()
        self._keydown_type = -1

    def start(self) -> bool:
        """Arm the tap on its own run-loop thread; False if Quartz is missing or the grant is absent."""
        self._ready.clear()
        self._armed = False
        self._thread = threading.Thread(target=self._run, name="holo-esc-tap", daemon=True)
        self._thread.start()
        self._ready.wait(timeout=START_TIMEOUT_S)
        return self._armed

    def stop(self) -> None:
        """Stop the run loop and join its thread."""
        quartz, loop = self._quartz, self._loop
        if quartz is not None and loop is not None:
            quartz.CFRunLoopStop(loop)
        thread = self._thread
        if thread is not None:
            thread.join(timeout=STOP_JOIN_TIMEOUT_S)
        self._thread = None
        self._loop = None

    def _run(self) -> None:
        try:
            import Quartz
        except Exception:
            logger.warning("Quartz is unavailable; the Esc kill switch is disabled")
            self._ready.set()
            return

        self._quartz = Quartz
        self._disabled_types = (Quartz.kCGEventTapDisabledByTimeout, Quartz.kCGEventTapDisabledByUserInput)
        self._keydown_type = Quartz.kCGEventKeyDown

        tap = Quartz.CGEventTapCreate(
            Quartz.kCGSessionEventTap,
            Quartz.kCGHeadInsertEventTap,
            Quartz.kCGEventTapOptionListenOnly,
            Quartz.CGEventMaskBit(Quartz.kCGEventKeyDown),
            self._handler,
            None,
        )
        if tap is None:
            logger.warning("could not create the Esc event tap (grant Input Monitoring?)")
            self._ready.set()
            return

        self._tap = tap
        source = Quartz.CFMachPortCreateRunLoopSource(None, tap, 0)
        self._loop = Quartz.CFRunLoopGetCurrent()
        Quartz.CFRunLoopAddSource(self._loop, source, Quartz.kCFRunLoopDefaultMode)
        Quartz.CGEventTapEnable(tap, True)
        self._armed = True
        self._ready.set()
        Quartz.CFRunLoopRun()

    def _handler(self, proxy: object, event_type: int, event: object, refcon: object) -> object:
        quartz = self._quartz
        assert quartz is not None  # the handler only fires after _run imported Quartz
        # A disable sentinel carries no usable event payload, so only read the keycode for a keydown.
        keycode = (
            quartz.CGEventGetIntegerValueField(event, quartz.kCGKeyboardEventKeycode)
            if event_type == self._keydown_type
            else -1
        )
        decision = classify_tap_event(
            event_type,
            keycode,
            disabled_types=self._disabled_types,
            keydown_type=self._keydown_type,
            esc_keycode=ESC_KEYCODE,
        )
        try:
            if decision is EscTapDecision.REENABLE:
                quartz.CGEventTapEnable(self._tap, True)
                logger.warning("kill switch: macOS disabled the Esc tap; re-enabled it")
            elif decision is EscTapDecision.FORWARD_ESC and self._switch.on_press(
                is_stop_key=True, now=time.monotonic()
            ):
                logger.warning("kill switch: Esc stop gesture detected; requesting stop")
        except Exception:
            logger.warning("kill-switch tap handler failed", exc_info=True)
        return event
