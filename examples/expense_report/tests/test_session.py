"""Behavioural tests for the session layer against a real fake-mode runtime.

`SpawnConfig(fake=True)` spawns the actual hai-agent-runtime binary with no
model and no desktop control, so these tests exercise the real spawn/HTTP/
stream/persist path end-to-end. Skipped when the binary is not available.
"""

from __future__ import annotations

import json
import shutil
import socket
from pathlib import Path

import pytest
from agp_types import TrajectoryStatus
from hai_agents.local.install import installed_binary
from hai_agents.local.manifest import BINARY_NAME, PINNED_RUNTIME_VERSION
from holo_desktop.agent_client.session_runner import TurnOutcome
from holo_desktop.settings import AUTH_TOKEN_ENV

from expense_report_demo.session import Runtime, RuntimeConfig, TaskResult, _project_result

_RUNTIME_AVAILABLE = shutil.which(BINARY_NAME) is not None or installed_binary(PINNED_RUNTIME_VERSION) is not None

needs_runtime = pytest.mark.skipif(not _RUNTIME_AVAILABLE, reason="hai-agent-runtime binary not installed")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _fake_config() -> RuntimeConfig:
    return RuntimeConfig(port=_free_port(), model=None, base_url=None, fake=True)


def test_project_result_interrupted_keeps_session_id() -> None:
    """A kill-switch stop resets the session, but the result still reports the id it ran against."""
    outcome = TurnOutcome(status=TrajectoryStatus.INTERRUPTED, answer="", error=None, session_id="sess-1")
    result = _project_result(outcome, n_steps=3)
    assert result.status == "interrupted"
    assert result.session_id == "sess-1"
    assert result.n_steps == 3
    assert result.answer is None


def test_project_result_completed_carries_answer() -> None:
    outcome = TurnOutcome(status=TrajectoryStatus.COMPLETED, answer="pong", error=None, session_id="sess-2")
    result = _project_result(outcome, n_steps=1)
    assert result.status == "completed"
    assert result.answer == "pong"


def test_project_result_sessionless_stop_reports_empty_id() -> None:
    """A stop that won before any session was created has no id to report — "" , not a crash."""
    outcome = TurnOutcome(status=TrajectoryStatus.INTERRUPTED, answer="", error=None, session_id=None)
    result = _project_result(outcome, n_steps=0)
    assert result.session_id == ""


def test_project_result_non_terminal_status_raises() -> None:
    outcome = TurnOutcome(status=None, answer="", error=None, session_id="sess-3")
    with pytest.raises(RuntimeError, match="non-terminal"):
        _project_result(outcome, n_steps=0)


def test_run_task_outside_context_raises(tmp_path: Path) -> None:
    runtime = Runtime(_fake_config())
    with pytest.raises(RuntimeError, match="context"):
        runtime.run_task(
            task="noop", max_steps=1, max_time_s=10.0, events_path=tmp_path / "events.jsonl", expand_feed=False
        )


@pytest.mark.timeout(60)
def test_runtime_attaches_to_fake_server_non_fake(
    monkeypatch: pytest.MonkeyPatch, fake_agent_server: int, tmp_path: Path
) -> None:
    """Non-fake `Runtime` against a fake agent server: exercises the real
    `require_api_key(settings=)` and `ensure_local_runtime(settings=)` wiring without
    the runtime binary."""
    monkeypatch.setenv(AUTH_TOKEN_ENV, "test-token")
    monkeypatch.setenv("HAI_API_KEY", "test-key")  # satisfy require_api_key without interactive login
    config = RuntimeConfig(port=fake_agent_server, model=None, base_url=None, fake=False)
    with Runtime(config) as runtime:
        result = runtime.run_task(
            task="Reply with the word pong.",
            max_steps=5,
            max_time_s=60.0,
            events_path=tmp_path / "events.jsonl",
            expand_feed=False,
        )

    assert result.status == "completed", f"unexpected status: {result.status} ({result.error})"
    assert result.session_id == "fake-session"


@needs_runtime
def test_run_task_completes_and_persists_events(tmp_path: Path) -> None:
    events_path = tmp_path / "deep" / "events.jsonl"
    with Runtime(_fake_config()) as runtime:
        result = runtime.run_task(
            task="Reply with the word pong.",
            max_steps=5,
            max_time_s=120.0,
            events_path=events_path,
            expand_feed=False,
        )

    assert isinstance(result, TaskResult)
    assert result.status == "completed", f"unexpected status: {result.status} ({result.error})"
    assert result.error is None
    assert result.answer, "fake runtime should produce an answer"
    assert result.session_id

    # Events were streamed to our own JSONL, one parseable TrajectoryEvent per line.
    assert events_path.is_file()
    lines = [line for line in events_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert lines, "expected at least one persisted event"
    for line in lines:
        record = json.loads(line)
        assert "type" in record
        assert "timestamp" in record


@needs_runtime
def test_run_task_persists_observations_and_captures_answer(tmp_path: Path) -> None:
    """Fake mode answers without policy steps: n_steps is 0, observation events
    land in the JSONL, and the answer is carried on the result."""
    events_path = tmp_path / "events.jsonl"
    with Runtime(_fake_config()) as runtime:
        result = runtime.run_task(
            task="Reply with the word pong.",
            max_steps=5,
            max_time_s=120.0,
            events_path=events_path,
            expand_feed=False,
        )
    assert result.n_steps == 0
    assert result.answer, "the answer is captured on the result"
    kinds = [
        (json.loads(line).get("data") or {}).get("kind")
        for line in events_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert "observation_event" in kinds


@needs_runtime
def test_runtime_reusable_for_sequential_tasks(tmp_path: Path) -> None:
    """One spawned runtime serves several sequential tasks without respawning."""
    with Runtime(_fake_config()) as runtime:
        first = runtime.run_task(
            task="Reply with one.", max_steps=5, max_time_s=120.0, events_path=tmp_path / "one.jsonl", expand_feed=False
        )
        second = runtime.run_task(
            task="Reply with two.", max_steps=5, max_time_s=120.0, events_path=tmp_path / "two.jsonl", expand_feed=False
        )
    assert first.status == "completed"
    assert second.status == "completed"
    assert first.session_id != second.session_id
