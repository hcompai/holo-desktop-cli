"""Behavioural tests for the macOS first-run permission walkthrough in `holo run`.

TCC grants only latch after the runtime restarts, so the first task against a
freshly installed managed runtime that fails with a permission-shaped error
must be retried exactly once with a fresh runtime process. The heuristic and
first-run marker live in agent_client.permissions now; the runtime's stderr
arrives as the SDK's ``runtime.log_path``.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

from holo_desktop.agent_client import permissions

run_mod = importlib.import_module("holo_desktop.cli.run")


@pytest.fixture(autouse=True)
def first_run_marker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    marker = tmp_path / "marker" / ".first-run-complete"
    monkeypatch.setattr(permissions, "FIRST_RUN_MARKER", marker)
    return marker


def test_first_run_pending_until_marked_complete() -> None:
    assert permissions.first_run_pending()
    permissions.mark_first_run_complete()
    assert not permissions.first_run_pending()


def test_log_tail_heuristic_reads_the_sdk_log_path(tmp_path: Path) -> None:
    log = tmp_path / "runtime.log"
    log.write_bytes(b"boring startup\n" + b"could not create image from display\n")
    assert permissions.log_tail_suggests_permissions(log) is True
    assert permissions.log_tail_suggests_permissions(tmp_path / "absent.log") is False
    assert permissions.log_tail_suggests_permissions(None) is False


def test_log_tail_detects_permission_shaped_errors(tmp_path: Path) -> None:
    log = tmp_path / "hai-agent-runtime-12345.log"

    assert not permissions.log_tail_suggests_permissions(log), "missing log must not match"

    log.write_text("error: screen recording permission denied by TCC\n", encoding="utf-8")
    assert permissions.log_tail_suggests_permissions(log)

    log.write_text("error: connection refused\n", encoding="utf-8")
    assert not permissions.log_tail_suggests_permissions(log)


def test_text_detects_permission_shaped_errors() -> None:
    assert permissions.text_suggests_permissions("screen recording not permitted")
    assert permissions.text_suggests_permissions("Accessibility access denied by TCC")
    assert permissions.text_suggests_permissions("could not create image from display")
    assert not permissions.text_suggests_permissions("model endpoint 500")
    assert not permissions.text_suggests_permissions("")


def _run_with_scripted_drive(
    monkeypatch: pytest.MonkeyPatch,
    outcomes: list[tuple[str | None, str | None, str | None]],
    spawned: bool,
    log_path: Path | None = None,
) -> int:
    """Drive `run()` with a scripted `_drive`; returns how many attempts were made.

    `spawned` mirrors ``runtime.owned``: True when this process owns the runtime,
    False when it attached to one started by another Holo surface. ``log_path``
    is what the SDK reported as the runtime's stderr log.
    """
    calls: list[object] = []

    async def fake_drive(**kwargs: object) -> tuple[str | None, str | None, str | None, bool, Path | None]:
        calls.append(kwargs)
        answer, status, error = outcomes[len(calls) - 1]
        return answer, status, error, spawned, log_path

    monkeypatch.setattr(run_mod, "_drive", fake_drive)
    monkeypatch.setenv("HAI_API_KEY", "key")
    monkeypatch.setenv("PATH", "/nonexistent")
    run_mod.run("do the thing", quiet=True)
    return len(calls)


@pytest.mark.skipif(sys.platform != "darwin", reason="walkthrough is macOS-only")
def test_permission_failure_on_first_managed_run_retries_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    log = tmp_path / "logs" / "hai-agent-runtime.log"
    log.parent.mkdir()
    log.write_text("accessibility not granted", encoding="utf-8")

    attempts = _run_with_scripted_drive(
        monkeypatch,
        [(None, "failed", "permission boom"), ("done", "completed", None)],
        spawned=True,
        log_path=log,
    )
    assert attempts == 2
    assert not permissions.first_run_pending(), "a completed retry must mark the first run done"


@pytest.mark.skipif(sys.platform != "darwin", reason="walkthrough is macOS-only")
def test_permission_shaped_session_error_retries_even_without_log_match(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The runtime may report TCC failures only via the agent API, never via stderr."""
    log = tmp_path / "logs" / "hai-agent-runtime.log"
    log.parent.mkdir()
    log.write_text("model endpoint 500", encoding="utf-8")

    attempts = _run_with_scripted_drive(
        monkeypatch,
        [(None, "failed", "screen recording not permitted"), ("done", "completed", None)],
        spawned=True,
        log_path=log,
    )
    assert attempts == 2


@pytest.mark.skipif(sys.platform != "darwin", reason="walkthrough is macOS-only")
def test_permission_shaped_session_error_retries_with_missing_log(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts = _run_with_scripted_drive(
        monkeypatch,
        [(None, "failed", "accessibility access denied by TCC"), ("done", "completed", None)],
        spawned=True,
        log_path=None,
    )
    assert attempts == 2


@pytest.mark.skipif(sys.platform != "darwin", reason="walkthrough is macOS-only")
def test_non_permission_failure_does_not_retry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    log = tmp_path / "logs" / "hai-agent-runtime.log"
    log.parent.mkdir()
    log.write_text("model endpoint 500", encoding="utf-8")

    with pytest.raises(SystemExit):
        _run_with_scripted_drive(
            monkeypatch, [(None, "failed", "boom"), ("never", "completed", None)], spawned=True, log_path=log
        )


def test_missing_terminal_status_exits_nonzero(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as exc:
        _run_with_scripted_drive(monkeypatch, [(None, None, None)], spawned=True)

    assert exc.value.code == 1
    assert "session ended without terminal status" in capsys.readouterr().err


@pytest.mark.skipif(sys.platform != "darwin", reason="walkthrough is macOS-only")
def test_completed_runs_after_first_do_not_recheck(monkeypatch: pytest.MonkeyPatch) -> None:
    permissions.mark_first_run_complete()
    attempts = _run_with_scripted_drive(monkeypatch, [("done", "completed", None)], spawned=True)
    assert attempts == 1


@pytest.mark.skipif(sys.platform != "darwin", reason="walkthrough is macOS-only")
def test_attach_mode_permission_failure_warns_instead_of_retrying(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An attached runtime belongs to another Holo process: shutting it down is not
    ours to do, so a retry would reuse the same process and TCC grants would still
    not latch. Instead of a futile retry behind a false "restarting" message, point
    the user at the owning process."""
    # A single scripted outcome: a second attempt would IndexError, failing the test.
    with pytest.raises(SystemExit):
        _run_with_scripted_drive(
            monkeypatch, [(None, "failed", "screen recording not permitted")], spawned=False, log_path=None
        )

    err_text = capsys.readouterr().err.replace("\n", " ").lower()
    assert "another holo process" in err_text
    assert "restart" in err_text
    assert "restarting the runtime and retrying" not in err_text, "must not claim a restart it cannot perform"
    assert permissions.first_run_pending(), "a failed attach-mode first run must stay pending"
