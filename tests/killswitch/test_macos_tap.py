"""The Esc tap classifies events correctly and stays alive after macOS disables it."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from holo_desktop.killswitch import channel
from holo_desktop.killswitch.channel import StopSentinel
from holo_desktop.killswitch.gesture import StopKeySwitch
from holo_desktop.killswitch.macos_tap import (
    ESC_KEYCODE,
    EscTapDecision,
    QuartzEscTap,
    classify_tap_event,
)

# Stand-ins for the Quartz constants; their exact values are irrelevant to the decision logic.
_DISABLED = (0xFFFFFFFE, 0xFFFFFFFF)
_KEYDOWN = 10
_KWARGS = {"disabled_types": _DISABLED, "keydown_type": _KEYDOWN, "esc_keycode": ESC_KEYCODE}


@pytest.fixture(autouse=True)
def _isolate_channel(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(channel, "STOP_PATH", tmp_path / "stop")


def test_disable_sentinels_request_a_reenable() -> None:
    for disabled_type in _DISABLED:
        assert classify_tap_event(disabled_type, -1, **_KWARGS) is EscTapDecision.REENABLE


def test_esc_keydown_is_forwarded() -> None:
    assert classify_tap_event(_KEYDOWN, ESC_KEYCODE, **_KWARGS) is EscTapDecision.FORWARD_ESC


def test_non_esc_keydown_is_ignored() -> None:
    assert classify_tap_event(_KEYDOWN, ESC_KEYCODE + 1, **_KWARGS) is EscTapDecision.IGNORE


def test_esc_keycode_outside_a_keydown_is_ignored() -> None:
    assert classify_tap_event(_KEYDOWN + 999, ESC_KEYCODE, **_KWARGS) is EscTapDecision.IGNORE


class _FakeQuartz:
    """The slice of Quartz the tap handler calls; the event payload is the keycode itself."""

    kCGKeyboardEventKeycode = 9

    def __init__(self) -> None:
        self.reenable_calls = 0

    def CGEventGetIntegerValueField(self, event: object, field: int) -> int:
        assert isinstance(event, int)
        return event

    def CGEventTapEnable(self, tap: object, enabled: bool) -> None:
        assert enabled is True
        self.reenable_calls += 1


def _wire_tap(switch: StopKeySwitch) -> tuple[QuartzEscTap, _FakeQuartz]:
    """A QuartzEscTap with Quartz stubbed, as if ``_run`` had already armed it."""
    tap = QuartzEscTap(switch)
    fake = _FakeQuartz()
    tap._quartz = fake
    tap._tap = object()
    tap._disabled_types = _DISABLED
    tap._keydown_type = _KEYDOWN
    return tap, fake


def test_tap_reenables_and_still_fires_after_macos_disables_it() -> None:
    """The bug: a disabled tap must heal and keep detecting the Esc gesture, not go deaf."""
    switch = StopKeySwitch(taps=2, window_s=0.6)
    tap, fake = _wire_tap(switch)

    tap._handler(None, _DISABLED[0], None, None)
    assert fake.reenable_calls == 1

    tap._handler(None, _KEYDOWN, ESC_KEYCODE, None)
    tap._handler(None, _KEYDOWN, ESC_KEYCODE, None)

    assert StopSentinel(started_at=time.time() - 10.0).stop_requested() is True


def test_single_esc_tap_after_reenable_does_not_fire() -> None:
    switch = StopKeySwitch(taps=2, window_s=0.6)
    tap, _ = _wire_tap(switch)

    tap._handler(None, _DISABLED[1], None, None)
    tap._handler(None, _KEYDOWN, ESC_KEYCODE, None)

    assert StopSentinel(started_at=time.time() - 10.0).stop_requested() is False
