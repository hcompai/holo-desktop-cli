"""Behavioural tests for the macOS first-run permission walkthrough in `holo run`.

TCC grants only latch after the runtime restarts, so the first task against a
freshly installed managed runtime that fails with a permission-shaped error
must be retried exactly once with a fresh runtime process.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

from holo_desktop.agent_client import launcher, runtime_install

run_mod = importlib.import_module("holo_desktop.cli.run")


@pytest.fixture()
def runtime_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    target = tmp_path / "runtime"
    monkeypatch.setattr(runtime_install, "RUNTIME_DIR", target)
    return target


def test_first_run_pending_until_marked_complete(runtime_dir: Path) -> None:
    assert runtime_install.first_run_pending(runtime_install.PINNED_RUNTIME_VERSION)
    runtime_install.mark_first_run_complete(runtime_install.PINNED_RUNTIME_VERSION)
    assert not runtime_install.first_run_pending(runtime_install.PINNED_RUNTIME_VERSION)


def test_log_tail_detects_permission_shaped_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(launcher, "LOG_DIR", tmp_path)
    port = 12345
    log = tmp_path / f"hai-agent-runtime-{port}.log"

    assert not launcher.log_tail_suggests_permissions(port), "missing log must not match"

    log.write_text("error: screen recording permission denied by TCC\n", encoding="utf-8")
    assert launcher.log_tail_suggests_permissions(port)

    log.write_text("error: connection refused\n", encoding="utf-8")
    assert not launcher.log_tail_suggests_permissions(port)


def test_text_detects_permission_shaped_errors() -> None:
    assert launcher.text_suggests_permissions("screen recording not permitted")
    assert launcher.text_suggests_permissions("Accessibility access denied by TCC")
    assert launcher.text_suggests_permissions("could not create image from display")
    assert not launcher.text_suggests_permissions("model endpoint 500")
    assert not launcher.text_suggests_permissions("")


# Pinned so the log file the walkthrough inspects matches the resolved port
# regardless of HAI_AGENT_RUNTIME_PORT leakage from other tests' dotenv loads.
TEST_PORT = 23499


def _run_with_scripted_drive(
    monkeypatch: pytest.MonkeyPatch,
    outcomes: list[tuple[str | None, str | None, str | None]],
    spawned: bool,
) -> int:
    """Drive `run()` with a scripted `_drive`; returns how many attempts were made.

    `spawned` mirrors what `ensure_running` reports: True when this process owns
    the runtime, False when it attached to one started by another Holo surface.
    """
    calls: list[object] = []

    async def fake_drive(**kwargs: object) -> tuple[str | None, str | None, str | None, bool]:
        calls.append(kwargs)
        answer, status, error = outcomes[len(calls) - 1]
        return answer, status, error, spawned

    monkeypatch.setattr(run_mod, "_drive", fake_drive)
    monkeypatch.setenv("HAI_API_KEY", "key")
    monkeypatch.setenv(launcher.PORT_ENV, str(TEST_PORT))
    monkeypatch.setenv("PATH", "/nonexistent")
    run_mod.run("do the thing", quiet=True)
    return len(calls)


@pytest.mark.skipif(sys.platform != "darwin", reason="walkthrough is macOS-only")
def test_permission_failure_on_first_managed_run_retries_once(
    runtime_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    monkeypatch.setattr(launcher, "LOG_DIR", log_dir)
    (log_dir / f"hai-agent-runtime-{TEST_PORT}.log").write_text("accessibility not granted", encoding="utf-8")

    attempts = _run_with_scripted_drive(
        monkeypatch, [(None, "failed", "permission boom"), ("done", "completed", None)], spawned=True
    )
    assert attempts == 2
    assert not runtime_install.first_run_pending(runtime_install.PINNED_RUNTIME_VERSION), (
        "a completed retry must mark the first run done"
    )


@pytest.mark.skipif(sys.platform != "darwin", reason="walkthrough is macOS-only")
def test_permission_shaped_session_error_retries_even_without_log_match(
    runtime_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The runtime may report TCC failures only via the agent API, never via stderr."""
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    monkeypatch.setattr(launcher, "LOG_DIR", log_dir)
    (log_dir / f"hai-agent-runtime-{TEST_PORT}.log").write_text("model endpoint 500", encoding="utf-8")

    attempts = _run_with_scripted_drive(
        monkeypatch, [(None, "failed", "screen recording not permitted"), ("done", "completed", None)], spawned=True
    )
    assert attempts == 2


@pytest.mark.skipif(sys.platform != "darwin", reason="walkthrough is macOS-only")
def test_permission_shaped_session_error_retries_with_missing_log(
    runtime_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(launcher, "LOG_DIR", tmp_path / "no-such-dir")

    attempts = _run_with_scripted_drive(
        monkeypatch, [(None, "failed", "accessibility access denied by TCC"), ("done", "completed", None)], spawned=True
    )
    assert attempts == 2


@pytest.mark.skipif(sys.platform != "darwin", reason="walkthrough is macOS-only")
def test_non_permission_failure_does_not_retry(
    runtime_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    monkeypatch.setattr(launcher, "LOG_DIR", log_dir)
    (log_dir / f"hai-agent-runtime-{TEST_PORT}.log").write_text("model endpoint 500", encoding="utf-8")

    with pytest.raises(SystemExit):
        _run_with_scripted_drive(monkeypatch, [(None, "failed", "boom"), ("never", "completed", None)], spawned=True)


def test_missing_terminal_status_exits_nonzero(
    runtime_dir: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as exc:
        _run_with_scripted_drive(monkeypatch, [(None, None, None)], spawned=True)

    assert exc.value.code == 1
    assert "session ended without terminal status" in capsys.readouterr().err


@pytest.mark.skipif(sys.platform != "darwin", reason="walkthrough is macOS-only")
def test_completed_runs_after_first_do_not_recheck(runtime_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runtime_install.mark_first_run_complete(runtime_install.PINNED_RUNTIME_VERSION)
    attempts = _run_with_scripted_drive(monkeypatch, [("done", "completed", None)], spawned=True)
    assert attempts == 1


@pytest.mark.skipif(sys.platform != "darwin", reason="walkthrough is macOS-only")
def test_attach_mode_permission_failure_warns_instead_of_retrying(
    runtime_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An attached runtime belongs to another Holo process: `aclose()` is a no-op,
    so a retry would reuse the same process and TCC grants would still not latch.
    Instead of a futile retry behind a false "restarting" message, point the user
    at the owning process."""
    monkeypatch.setattr(launcher, "LOG_DIR", tmp_path / "no-such-dir")

    # A single scripted outcome: a second attempt would IndexError, failing the test.
    with pytest.raises(SystemExit):
        _run_with_scripted_drive(monkeypatch, [(None, "failed", "screen recording not permitted")], spawned=False)

    err_text = capsys.readouterr().err.replace("\n", " ").lower()
    assert "another holo process" in err_text
    assert "restart" in err_text
    assert "restarting the runtime and retrying" not in err_text, "must not claim a restart it cannot perform"
    assert runtime_install.first_run_pending(runtime_install.PINNED_RUNTIME_VERSION), (
        "a failed attach-mode first run must stay pending"
    )
