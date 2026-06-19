"""Behavioural tests for the `expense-report-demo run` subcommand.

The dry-run path returns before any app launch, fixture download, or runtime
spawn, so it exercises the real `port_from_env(settings=...)` wiring and
`HoloKwargs` construction without the `hai-agent-runtime` binary.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from holo_desktop.settings import PORT_ENV

import expense_report_demo.cli as cli_mod
from expense_report_demo.cli import run
from expense_report_demo.demos.runner import Demo, DemoOutcome, DemoRun
from expense_report_demo.demos.runner import run_demo as real_run_demo
from expense_report_demo.holo_kwargs import HoloKwargs


def test_run_dry_run_resolves_port_from_env(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    sentinel_port = 54321
    monkeypatch.setenv(PORT_ENV, str(sentinel_port))

    run("expense_report", dry_run=True)

    out = capsys.readouterr().out
    assert str(sentinel_port) in out, "dry-run should resolve the agent port from the environment"


def _run_demo_returning(outcome: DemoOutcome) -> Callable[..., DemoRun]:
    """Stand-in for run_demo that yields a valid DemoRun with `outcome`, built off the dry-run path."""

    def _fake(demo: Demo, kwargs: HoloKwargs, out: Path, **_kw: object) -> DemoRun:
        run_record = real_run_demo(
            demo, kwargs, out, dry_run=True, hooks=None, verifier=None, expand_feed=False, profile=False
        )
        return run_record.model_copy(update={"outcome": outcome, "error": "boom"})

    return _fake


def test_run_error_outcome_exits_1(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli_mod, "run_demo", _run_demo_returning("error"))
    with pytest.raises(SystemExit) as exc:
        run("expense_report")
    assert exc.value.code == 1


def test_run_interrupted_outcome_exits_130(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli_mod, "run_demo", _run_demo_returning("interrupted"))
    with pytest.raises(SystemExit) as exc:
        run("expense_report")
    assert exc.value.code == 130


def test_run_ok_outcome_does_not_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli_mod, "run_demo", _run_demo_returning("ok"))
    run("expense_report")  # no SystemExit on success
