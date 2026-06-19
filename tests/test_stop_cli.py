"""`holo stop` files a stop request; `--force` kills the runtime pids it discovers."""

from __future__ import annotations

from pathlib import Path

import pytest

from holo_desktop.agent_client import launcher
from holo_desktop.cli.stop import stop
from holo_desktop.killswitch import channel
from holo_desktop.killswitch.channel import StopSentinel


@pytest.fixture(autouse=True)
def _isolate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(channel, "STOP_PATH", tmp_path / "stop")
    monkeypatch.setattr(launcher, "TOKEN_DIR", tmp_path)


def test_stop_files_a_fresh_request() -> None:
    before = StopSentinel(started_at=_now_floor())
    assert before.stop_requested() is False
    stop()
    assert before.stop_requested() is True


def test_force_kills_discovered_runtime_pids(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "agent-pid-18795").write_text("4242", encoding="utf-8")
    (tmp_path / "agent-pid-9000").write_text("4243", encoding="utf-8")
    killed: list[int] = []
    monkeypatch.setattr(launcher, "kill_runtime_by_pid", lambda pid: killed.append(pid) or True)

    stop(force=True)

    assert sorted(killed) == [4242, 4243]


def test_force_targets_only_the_requested_port(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "agent-pid-18795").write_text("4242", encoding="utf-8")
    (tmp_path / "agent-pid-9000").write_text("4243", encoding="utf-8")
    killed: list[int] = []
    monkeypatch.setattr(launcher, "kill_runtime_by_pid", lambda pid: killed.append(pid) or True)

    stop(force=True, port=9000)

    assert killed == [4243]


def _now_floor() -> float:
    import time

    return time.time() - 1.0
