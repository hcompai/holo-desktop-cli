"""The listener picks the right per-platform backend, delegates to it, and arms with a typed outcome."""

from __future__ import annotations

import pytest

from holo_desktop.killswitch import listener
from holo_desktop.killswitch.gesture import StopKeySwitch
from holo_desktop.killswitch.listener import (
    KILL_SWITCH_UNAVAILABLE_HINT,
    ArmOutcome,
    PynputEscListener,
    arm_stop_listener,
    build_backend,
)
from holo_desktop.killswitch.macos_tap import QuartzEscTap


def test_arm_disabled_returns_none_and_disabled_outcome() -> None:
    assert arm_stop_listener(enabled=False) == (None, ArmOutcome.DISABLED)


def test_arm_unavailable_when_backend_cannot_start(monkeypatch: pytest.MonkeyPatch) -> None:
    """A backend that fails to start yields no listener and an UNAVAILABLE outcome the caller must surface."""

    class _DeadListener:
        def start(self) -> bool:
            return False

        def stop(self) -> None: ...

    monkeypatch.setattr(listener, "StopListener", _DeadListener)

    assert arm_stop_listener(enabled=True) == (None, ArmOutcome.UNAVAILABLE)


def test_arm_armed_returns_listener_and_armed_outcome(monkeypatch: pytest.MonkeyPatch) -> None:
    class _LiveListener:
        def start(self) -> bool:
            return True

        def stop(self) -> None: ...

    monkeypatch.setattr(listener, "StopListener", _LiveListener)

    arm_listener, outcome = arm_stop_listener(enabled=True)
    assert outcome is ArmOutcome.ARMED
    assert isinstance(arm_listener, _LiveListener)


def test_unavailable_hint_tells_the_user_how_to_recover() -> None:
    """The loud-warning contract: a failed arm must point the user at Input Monitoring."""
    assert "input monitoring" in KILL_SWITCH_UNAVAILABLE_HINT.lower()


def test_macos_uses_the_self_healing_quartz_tap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(listener.platform, "system", lambda: "Darwin")
    assert isinstance(build_backend(StopKeySwitch(2, 0.6)), QuartzEscTap)


def test_other_platforms_use_the_pynput_listener(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(listener.platform, "system", lambda: "Linux")
    assert isinstance(build_backend(StopKeySwitch(2, 0.6)), PynputEscListener)


def test_stop_listener_delegates_to_its_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    """StopListener is a thin façade: start/stop go straight to the platform backend."""
    calls: list[str] = []

    class _RecordingBackend:
        def start(self) -> bool:
            calls.append("start")
            return True

        def stop(self) -> None:
            calls.append("stop")

    monkeypatch.setattr(listener, "build_backend", lambda switch: _RecordingBackend())
    stop_listener = listener.StopListener()
    assert stop_listener.start() is True
    stop_listener.stop()
    assert calls == ["start", "stop"]
