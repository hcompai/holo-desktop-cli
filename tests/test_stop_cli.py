"""`holo stop` files a stop request; `--force` kills the runtime pids it discovers."""

from __future__ import annotations

import os
import subprocess
import sys
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


@pytest.fixture
def _pids_are_runtimes_except_4444(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(launcher, "process_is_runtime", lambda pid: pid != 4444)


def test_stop_files_a_fresh_request() -> None:
    before = StopSentinel(started_at=_now_floor())
    assert before.stop_requested() is False
    stop()
    assert before.stop_requested() is True


@pytest.mark.usefixtures("_pids_are_runtimes_except_4444")
def test_force_kills_discovered_runtime_pids(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "agent-pid-18795").write_text("4242", encoding="utf-8")
    (tmp_path / "agent-pid-9000").write_text("4243", encoding="utf-8")
    killed: list[int] = []
    monkeypatch.setattr(launcher, "kill_runtime_by_pid", lambda pid: killed.append(pid) or True)

    stop(force=True)

    assert sorted(killed) == [4242, 4243]


@pytest.mark.usefixtures("_pids_are_runtimes_except_4444")
def test_force_targets_only_the_requested_port(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "agent-pid-18795").write_text("4242", encoding="utf-8")
    (tmp_path / "agent-pid-9000").write_text("4243", encoding="utf-8")
    killed: list[int] = []
    monkeypatch.setattr(launcher, "kill_runtime_by_pid", lambda pid: killed.append(pid) or True)

    stop(force=True, port=9000)

    assert killed == [4243]


@pytest.mark.usefixtures("_pids_are_runtimes_except_4444")
def test_force_skips_pid_files_whose_pid_is_no_longer_a_runtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "agent-pid-18795").write_text("4444", encoding="utf-8")
    killed: list[int] = []
    monkeypatch.setattr(launcher, "kill_runtime_by_pid", lambda pid: killed.append(pid) or True)

    stop(force=True)

    assert killed == []


def test_process_is_runtime_rejects_dead_and_unrelated_pids() -> None:
    import os

    assert launcher.process_is_runtime(os.getpid()) is False
    assert launcher.process_is_runtime(2**22 - 1) is False


@pytest.mark.skipif(os.name != "posix", reason="tasklist reports image names only")
def test_process_is_runtime_matches_a_live_runtime_command_line() -> None:
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)", "hai-agent-runtime"])
    try:
        assert launcher.process_is_runtime(proc.pid) is True
    finally:
        proc.kill()
        proc.wait()


def _now_floor() -> float:
    import time

    return time.time() - 1.0
