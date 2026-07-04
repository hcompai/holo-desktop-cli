"""`holo stop` files a stop request; `--force` kills via SDK discovery plus legacy pid files."""

from __future__ import annotations

import importlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from holo_desktop.agent_client import legacy_state
from holo_desktop.cli.stop import stop
from holo_desktop.killswitch import channel
from holo_desktop.killswitch.channel import StopSentinel

# holo_desktop.cli.__init__ rebinds the `stop` attribute to the function, so reach
# the module object through importlib to patch its module-level LocalRuntime seam.
stop_module = importlib.import_module("holo_desktop.cli.stop")


@pytest.fixture(autouse=True)
def _isolate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(channel, "STOP_PATH", tmp_path / "stop")
    monkeypatch.setattr(legacy_state, "TOKEN_DIR", tmp_path)
    monkeypatch.setattr(
        stop_module.LocalRuntime, "attach", staticmethod(lambda *, port=None, cache_dir=None: None)
    )


def test_stop_files_a_fresh_request() -> None:
    before = StopSentinel(started_at=_now_floor())
    assert before.stop_requested() is False
    stop()
    assert before.stop_requested() is True


def test_force_kills_the_sdk_discovered_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    kills: list[int] = []
    runtime = SimpleNamespace(pid=4242, force_kill=lambda: kills.append(4242))
    monkeypatch.setattr(
        stop_module.LocalRuntime, "attach", staticmethod(lambda *, port=None, cache_dir=None: runtime)
    )

    stop(force=True, port=9000)

    assert kills == [4242]


def test_force_still_kills_legacy_pre_sdk_pid_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # One-release compat: a runtime spawned by a pre-SDK holo left ~/.holo/agent-pid-<port>;
    # an upgraded holo must still be able to stop it.
    (tmp_path / "agent-pid-18795").write_text("4242", encoding="utf-8")
    (tmp_path / "agent-pid-9000").write_text("4243", encoding="utf-8")
    killed: list[int] = []
    monkeypatch.setattr(legacy_state, "kill_runtime_by_pid", lambda pid: killed.append(pid) or True)

    stop(force=True)

    assert sorted(killed) == [4242, 4243]


def test_legacy_force_targets_only_the_requested_port(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "agent-pid-18795").write_text("4242", encoding="utf-8")
    (tmp_path / "agent-pid-9000").write_text("4243", encoding="utf-8")
    killed: list[int] = []
    monkeypatch.setattr(legacy_state, "kill_runtime_by_pid", lambda pid: killed.append(pid) or True)

    stop(force=True, port=9000)

    assert killed == [4243]


def _now_floor() -> float:
    import time

    return time.time() - 1.0
