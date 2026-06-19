"""The stop channel is a wall-clock signal: a turn honors only requests filed after it began."""

from __future__ import annotations

from pathlib import Path

import pytest

from holo_desktop.killswitch import channel
from holo_desktop.killswitch.channel import StopSentinel, request_stop


@pytest.fixture(autouse=True)
def _isolate_channel(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(channel, "STOP_PATH", tmp_path / "stop")


def test_request_after_turn_start_is_honored() -> None:
    sentinel = StopSentinel(started_at=200.0)
    assert sentinel.stop_requested() is False
    request_stop(now=300.0)
    assert sentinel.stop_requested() is True


def test_stale_request_before_turn_start_is_ignored() -> None:
    request_stop(now=100.0)
    sentinel = StopSentinel(started_at=200.0)
    assert sentinel.stop_requested() is False


def test_no_request_means_no_stop() -> None:
    assert StopSentinel(started_at=0.0).stop_requested() is False


def test_malformed_channel_does_not_stop(tmp_path: Path) -> None:
    (tmp_path / "stop").write_text("not-a-timestamp")
    assert StopSentinel(started_at=0.0).stop_requested() is False


def test_unreadable_channel_reads_as_no_stop(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A read error must not propagate: the kill-switch poll relies on this never raising."""
    a_directory = tmp_path / "stop-dir"
    a_directory.mkdir()
    monkeypatch.setattr(channel, "STOP_PATH", a_directory)  # reading a directory raises OSError
    assert StopSentinel(started_at=0.0).stop_requested() is False
