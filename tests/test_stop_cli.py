"""`holo stop` files a stop request; `--force` kills the runtime pids it discovers."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from hai_agents_local.runtime import process as runtime_process
from hai_agents_local.runtime import state as runtime_state

from holo_desktop.agent_client import launcher
from holo_desktop.cli.stop import stop
from holo_desktop.killswitch import channel
from holo_desktop.killswitch.channel import StopSentinel


@pytest.fixture(autouse=True)
def _isolate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(channel, "STOP_PATH", tmp_path / "stop")
    monkeypatch.setattr(launcher, "LEGACY_STATE_DIR", tmp_path / "legacy")


@pytest.fixture
def _pids_are_runtimes_except_4444(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(launcher, "process_is_runtime", lambda pid: pid != 4444)


@pytest.fixture
def killed(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    pids: list[int] = []
    monkeypatch.setattr(runtime_process, "kill_process_group", lambda pid: pids.append(pid) or True)
    return pids


def _publish_pid(directory: Path, port: int, pid: int) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"agent-pid-{port}").write_text(str(pid), encoding="utf-8")


def test_stop_files_a_fresh_request() -> None:
    before = StopSentinel(started_at=_now_floor())
    assert before.stop_requested() is False
    stop()
    assert before.stop_requested() is True


@pytest.mark.usefixtures("_pids_are_runtimes_except_4444")
def test_force_kills_runtimes_from_shared_and_legacy_state(killed: list[int]) -> None:
    _publish_pid(runtime_state.state_dir(), 18795, 4242)
    _publish_pid(launcher.LEGACY_STATE_DIR, 9000, 4243)

    stop(force=True)

    assert sorted(killed) == [4242, 4243]


@pytest.mark.usefixtures("_pids_are_runtimes_except_4444")
def test_force_targets_only_the_requested_port(killed: list[int]) -> None:
    _publish_pid(runtime_state.state_dir(), 18795, 4242)
    _publish_pid(runtime_state.state_dir(), 9000, 4243)

    stop(force=True, port=9000)

    assert killed == [4243]


@pytest.mark.usefixtures("_pids_are_runtimes_except_4444")
def test_force_skips_pid_files_whose_pid_is_no_longer_a_runtime(killed: list[int]) -> None:
    _publish_pid(runtime_state.state_dir(), 18795, 4444)

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
