"""Behavioural tests for the macOS first-run permission walkthrough in `holo run`.

On the desktop recipe TCC grants only latch after the runtime restarts, so the
first task against a freshly installed managed runtime that fails with a
permission-shaped error must be retried exactly once with a fresh runtime process.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

from holo_desktop.agent_client import launcher, runtime_install
from holo_desktop.settings import PORT_ENV

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


def _write_runtime_log(port: int, text: str) -> Path:
    log = launcher.runtime_log_path(port)
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(text, encoding="utf-8")
    return log


def test_log_tail_detects_permission_shaped_errors() -> None:
    port = 12345
    assert not launcher.log_tail_suggests_permissions(port), "missing log must not match"

    log = _write_runtime_log(port, "error: screen recording permission denied by TCC\n")
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
    outcomes: list[tuple[str | None, str | None, str | None] | Exception],
    spawned: bool,
    fast: bool = True,
) -> int:
    """Drive `run()` with a scripted `_drive`; returns how many attempts were made.

    `spawned` mirrors what `ensure_running` reports: True when this process owns
    the runtime, False when it attached to one started by another Holo surface.
    `fast` selects the desktop recipe, the only one whose runtime holds the TCC grants.
    """
    calls: list[object] = []

    async def fake_drive(**kwargs: object) -> tuple[str | None, str | None, str | None, bool]:
        calls.append(kwargs)
        outcome = outcomes[len(calls) - 1]
        if isinstance(outcome, Exception):
            raise outcome
        answer, status, error = outcome
        return answer, status, error, spawned

    monkeypatch.setattr(run_mod, "_drive", fake_drive)
    monkeypatch.setenv("HAI_API_KEY", "key")
    monkeypatch.setenv(PORT_ENV, str(TEST_PORT))
    monkeypatch.setenv("PATH", "/nonexistent")
    run_mod.run("do the thing", quiet=True, fast=fast)
    return len(calls)


@pytest.mark.skipif(sys.platform != "darwin", reason="walkthrough is macOS-only")
def test_permission_failure_on_first_managed_run_retries_once(
    runtime_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_runtime_log(TEST_PORT, "accessibility not granted")

    attempts = _run_with_scripted_drive(
        monkeypatch, [(None, "failed", "permission boom"), ("done", "completed", None)], spawned=True
    )
    assert attempts == 2
    assert not runtime_install.first_run_pending(runtime_install.PINNED_RUNTIME_VERSION), (
        "a completed retry must mark the first run done"
    )


@pytest.mark.skipif(sys.platform != "darwin", reason="walkthrough is macOS-only")
def test_permission_shaped_session_error_retries_even_without_log_match(
    runtime_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The runtime may report TCC failures only via the agent API, never via stderr."""
    _write_runtime_log(TEST_PORT, "model endpoint 500")

    attempts = _run_with_scripted_drive(
        monkeypatch, [(None, "failed", "screen recording not permitted"), ("done", "completed", None)], spawned=True
    )
    assert attempts == 2


@pytest.mark.skipif(sys.platform != "darwin", reason="walkthrough is macOS-only")
def test_permission_shaped_session_error_retries_with_missing_log(
    runtime_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    attempts = _run_with_scripted_drive(
        monkeypatch, [(None, "failed", "accessibility access denied by TCC"), ("done", "completed", None)], spawned=True
    )
    assert attempts == 2


@pytest.mark.skipif(sys.platform != "darwin", reason="walkthrough is macOS-only")
def test_non_permission_failure_does_not_retry(runtime_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_runtime_log(TEST_PORT, "model endpoint 500")

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
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An attached runtime belongs to another Holo process: `aclose()` is a no-op,
    so a retry would reuse the same process and TCC grants would still not latch.
    Instead of a futile retry behind a false "restarting" message, point the user
    at the owning process."""
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


@pytest.mark.skipif(sys.platform != "darwin", reason="walkthrough is macOS-only")
def test_shared_recipe_never_restarts_the_runtime_for_grants(
    runtime_dir: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The shared recipe drives the desktop from this process, so a runtime restart cannot latch its grants."""
    _write_runtime_log(TEST_PORT, "accessibility not granted")

    with pytest.raises(SystemExit):
        _run_with_scripted_drive(
            monkeypatch, [(None, "failed", "screen recording not permitted")], spawned=True, fast=False
        )

    assert "restarting the runtime" not in capsys.readouterr().err


def test_preflight_permission_error_exits_with_its_guidance(
    runtime_dir: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as exc:
        _run_with_scripted_drive(monkeypatch, [PermissionError("grant your terminal")], spawned=True, fast=False)

    assert exc.value.code == 1
    assert "grant your terminal" in capsys.readouterr().err
