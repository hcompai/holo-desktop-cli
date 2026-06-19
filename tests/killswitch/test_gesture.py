"""The panic gesture fires only on N taps within a rolling window, and only the stop key files a stop."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from holo_desktop.killswitch import channel
from holo_desktop.killswitch.channel import StopSentinel
from holo_desktop.killswitch.gesture import MultiTapDetector, StopKeySwitch


@pytest.fixture(autouse=True)
def _isolate_channel(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(channel, "STOP_PATH", tmp_path / "stop")


def test_n_taps_within_window_fire_on_the_last() -> None:
    detector = MultiTapDetector(taps=3, window_s=0.6)
    assert detector.record(0.0) is False
    assert detector.record(0.2) is False
    assert detector.record(0.5) is True


def test_two_taps_fire_when_two_are_required() -> None:
    detector = MultiTapDetector(taps=2, window_s=0.6)
    assert detector.record(0.0) is False
    assert detector.record(0.3) is True


def test_fewer_taps_than_required_do_not_fire() -> None:
    detector = MultiTapDetector(taps=3, window_s=0.6)
    assert detector.record(0.0) is False
    assert detector.record(0.3) is False


def test_last_tap_outside_window_does_not_fire() -> None:
    detector = MultiTapDetector(taps=3, window_s=0.6)
    detector.record(0.0)
    detector.record(0.2)
    # 0.9 - 0.2 = 0.7 > 0.6, so only the 0.9 tap stays in the window.
    assert detector.record(0.9) is False


def test_resets_after_firing_so_a_lone_tap_does_not_refire() -> None:
    detector = MultiTapDetector(taps=2, window_s=0.6)
    assert detector.record(0.0) is False
    assert detector.record(0.2) is True
    # A single tap after a fire starts a fresh count.
    assert detector.record(0.4) is False


def test_sliding_window_ages_out_old_taps() -> None:
    detector = MultiTapDetector(taps=3, window_s=0.6)
    assert detector.record(0.0) is False
    assert detector.record(0.5) is False
    # Both earlier taps aged out (>0.6 ago), so this is a fresh first tap, not the third.
    assert detector.record(1.2) is False
    assert detector.record(1.5) is False
    assert detector.record(1.7) is True


def test_two_stop_key_taps_file_a_stop_request() -> None:
    started_at = time.time() - 10.0
    switch = StopKeySwitch(taps=2, window_s=0.6)
    assert switch.on_press(is_stop_key=True, now=0.0) is False
    assert switch.on_press(is_stop_key=True, now=0.3) is True
    assert StopSentinel(started_at=started_at).stop_requested() is True


def test_partial_gesture_does_not_fire() -> None:
    switch = StopKeySwitch(taps=2, window_s=0.6)
    switch.on_press(is_stop_key=True, now=0.0)
    assert StopSentinel(started_at=time.time() - 10.0).stop_requested() is False


def test_non_stop_keys_are_ignored() -> None:
    switch = StopKeySwitch(taps=2, window_s=0.6)
    for t in (0.0, 0.1, 0.2):
        assert switch.on_press(is_stop_key=False, now=t) is False
    assert StopSentinel(started_at=time.time() - 10.0).stop_requested() is False
