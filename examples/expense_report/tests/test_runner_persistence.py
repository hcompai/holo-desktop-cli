"""Behavioural tests for the runner's IO contract: dry-run shape, task.json content,
summary CSV append behaviour. We don't exercise a live session here — that's
covered by tests/test_session.py and real runs."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from expense_report_demo.demos import runner
from expense_report_demo.demos.runner import AppLaunchSpec, Demo, DemoRun, _persist, run_demo
from expense_report_demo.demos.verify import VerifyCheck
from expense_report_demo.holo_kwargs import HoloKwargs
from expense_report_demo.session import TaskResult


def _kwargs() -> HoloKwargs:
    return HoloKwargs(
        max_steps=1,
        max_time_s=1.0,
        model=None,
        llm_base_url=None,
        port=4823,
        fake=True,
    )


def _fixture_demo() -> Demo:
    return Demo(
        slug="test_demo",
        title="Test Demo",
        description="A fixture demo used only in tests.",
        fixtures_manifest=None,
        pre_launch=[
            AppLaunchSpec(
                bundle_id="com.apple.finder",
                urls=None,
                isolated_browser_session=False,
            ),
        ],
        focus_bundle_id="com.apple.finder",
        task="noop",
        max_steps=1,
        max_time_s=1.0,
    )


def test_dry_run_returns_ok_outcome(tmp_path: Path) -> None:
    demo = _fixture_demo()
    out = tmp_path / "runs"

    run = run_demo(demo, _kwargs(), out, dry_run=True, hooks=None, verifier=None, expand_feed=False, profile=False)
    assert run.outcome == "ok"
    assert run.run_id == "dry-run"
    assert run.session_id is None
    assert run.metrics is None
    assert run.verify_checks is None
    assert run.events_path == ""
    # No files written in dry-run.
    assert not out.exists()


def test_demo_pydantic_rejects_empty_pre_launch() -> None:
    """Demo requires at least one AppLaunchSpec; tests the Pydantic constraint, not an assertion."""
    with pytest.raises(Exception):  # noqa: B017 — Pydantic ValidationError
        Demo(
            slug="bad",
            title="Bad",
            description="Bad",
            fixtures_manifest=None,
            pre_launch=[],  # empty — must reject
            focus_bundle_id="com.apple.finder",
            task="noop",
            max_steps=1,
            max_time_s=1.0,
        )


def test_demo_pydantic_clamps_max_steps_range() -> None:
    with pytest.raises(Exception):  # noqa: B017
        Demo(
            slug="bad",
            title="Bad",
            description="Bad",
            fixtures_manifest=None,
            pre_launch=[
                AppLaunchSpec(
                    bundle_id="com.apple.finder",
                    urls=None,
                    isolated_browser_session=False,
                ),
            ],
            focus_bundle_id="com.apple.finder",
            task="noop",
            max_steps=10_000,  # over the cap of 500
            max_time_s=1.0,
        )


def test_persist_writes_task_json_and_appends_csv(tmp_path: Path) -> None:
    """Calling _persist directly with a synthetic DemoRun — proves the IO shape
    without needing a live session."""
    demo = _fixture_demo()
    checks = [
        VerifyCheck(name="ledger_rows", passed=True, reason="all rows present", failure_category=None),
        VerifyCheck(name="mail_draft", passed=False, reason="no draft", failure_category="agent"),
    ]
    run = DemoRun(
        demo=demo,
        holo_kwargs=_kwargs(),
        run_id="20260612-120000",
        session_id="sess-1",
        started_at="2026-06-12T00:00:00+00:00",
        ended_at="2026-06-12T00:00:01+00:00",
        elapsed_s=1.0,
        outcome="ok",
        error=None,
        answer="hello world",
        verify_checks=checks,
        events_path="runs/test_demo/20260612-120000/events.jsonl",
        metrics=None,
    )

    out = tmp_path / "runs"
    _persist(run, out)

    task_json = out / "test_demo" / "20260612-120000" / "task.json"
    assert task_json.is_file()
    payload = json.loads(task_json.read_text())
    assert payload["run_id"] == "20260612-120000"
    assert payload["session_id"] == "sess-1"
    assert payload["outcome"] == "ok"
    assert payload["demo"]["slug"] == "test_demo"
    assert payload["answer"] == "hello world"
    assert payload["verify_checks"][0]["name"] == "ledger_rows"
    assert payload["verify_checks"][1]["failure_category"] == "agent"

    csv_path = out / "summary-demos.csv"
    assert csv_path.is_file()
    rows = list(csv.DictReader(csv_path.open()))
    assert len(rows) == 1
    assert rows[0]["demo"] == "test_demo"
    assert rows[0]["outcome"] == "ok"
    assert rows[0]["verify_pass"] == "1/2"
    assert rows[0]["answer"] == "hello world"

    # Append a second run; the header should not be re-written.
    run2 = run.model_copy(update={"run_id": "20260612-130000", "answer": "second"})
    _persist(run2, out)
    rows2 = list(csv.DictReader(csv_path.open()))
    assert len(rows2) == 2
    assert {r["run_id"] for r in rows2} == {"20260612-120000", "20260612-130000"}


class _FakeRuntime:
    """Stands in for session.Runtime so run_demo's lifecycle runs without a daemon."""

    def __init__(self, *_args: object, **_kwargs: object) -> None: ...

    def __enter__(self) -> _FakeRuntime:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def run_task(self, **_kwargs: object) -> TaskResult:
        return TaskResult(session_id="sess-x", answer="done", status="completed", error=None, n_steps=0)


def _patch_session_boundaries(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub the side-effecting boundaries (app launch, runtime daemon) so run_demo's
    control flow runs hermetically — no macOS apps, no hai-agent-runtime binary."""
    monkeypatch.setattr(runner.apps, "kill_all", lambda *_a, **_k: None)
    monkeypatch.setattr(runner.apps, "activate_app", lambda *_a, **_k: None)
    monkeypatch.setattr(runner, "_launch_one", lambda *_a, **_k: None)
    monkeypatch.setattr(runner, "Runtime", _FakeRuntime)


def test_verifier_exception_is_recorded_and_run_persists(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A crashing verifier becomes a harness check; task.json + CSV are still written."""
    _patch_session_boundaries(monkeypatch)
    demo = _fixture_demo()
    out = tmp_path / "runs"

    def _boom_verifier(_demo: Demo) -> list[VerifyCheck]:
        raise ValueError("kaboom")

    run = run_demo(
        demo, _kwargs(), out, dry_run=False, hooks=None, verifier=_boom_verifier, expand_feed=False, profile=False
    )

    assert run.outcome == "ok"
    assert run.verify_checks is not None
    assert len(run.verify_checks) == 1
    check = run.verify_checks[0]
    assert check.name == "verifier"
    assert check.passed is False
    assert check.failure_category == "harness"
    assert "kaboom" in check.reason

    assert (out / demo.slug / run.run_id / "task.json").is_file()
    rows = list(csv.DictReader((out / "summary-demos.csv").open()))
    assert len(rows) == 1
    assert rows[0]["outcome"] == "ok"


def test_verifier_runs_when_session_times_out(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A non-completed session (timed_out/failed) is still graded — artifacts may exist."""

    class _TimedOutRuntime(_FakeRuntime):
        def run_task(self, **_kwargs: object) -> TaskResult:
            return TaskResult(session_id="s", answer=None, status="timed_out", error="ran out of time", n_steps=3)

    _patch_session_boundaries(monkeypatch)
    monkeypatch.setattr(runner, "Runtime", _TimedOutRuntime)
    demo = _fixture_demo()
    out = tmp_path / "runs"
    graded: list[str] = []

    def _verifier(demo_arg: Demo) -> list[VerifyCheck]:
        graded.append(demo_arg.slug)
        return [VerifyCheck(name="ledger", passed=True, reason="rows present", failure_category=None)]

    run = run_demo(
        demo, _kwargs(), out, dry_run=False, hooks=None, verifier=_verifier, expand_feed=False, profile=False
    )

    assert graded == [demo.slug]
    assert run.outcome == "error"
    assert run.verify_checks is not None
    assert run.verify_checks[0].name == "ledger"


def test_failed_run_echoes_error_and_runtime_log_to_stderr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A non-ok run surfaces its error reason and the runtime log pointer on stderr, not only in task.json."""

    class _FailingRuntime(_FakeRuntime):
        def run_task(self, **_kwargs: object) -> TaskResult:
            return TaskResult(
                session_id="s", answer=None, status="failed", error="ImportError: dlopen xxhash", n_steps=0
            )

    _patch_session_boundaries(monkeypatch)
    monkeypatch.setattr(runner, "Runtime", _FailingRuntime)

    run = run_demo(
        _fixture_demo(),
        _kwargs(),
        tmp_path / "runs",
        dry_run=False,
        hooks=None,
        verifier=None,
        expand_feed=False,
        profile=False,
    )

    assert run.outcome == "error"
    err = capsys.readouterr().err
    assert "ImportError: dlopen xxhash" in err
    assert "runtime log:" in err


def test_setup_failure_still_runs_teardown_and_persists(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """If a setup hook raises, teardown still runs and a run record is persisted."""
    _patch_session_boundaries(monkeypatch)
    demo = _fixture_demo()
    out = tmp_path / "runs"
    teardown_calls: list[str] = []

    def _setup(_demo: Demo) -> None:
        raise RuntimeError("staging blew up")

    def _teardown(demo_arg: Demo) -> None:
        teardown_calls.append(demo_arg.slug)

    run = run_demo(
        demo, _kwargs(), out, dry_run=False, hooks=(_setup, _teardown), verifier=None, expand_feed=False, profile=False
    )

    assert teardown_calls == [demo.slug]
    assert run.outcome == "error"
    assert "staging blew up" in (run.error or "")
    assert (out / demo.slug / run.run_id / "task.json").is_file()


def test_safe_verify_wraps_exception_as_harness_check() -> None:
    """_safe_verify turns a raising verifier into a single harness failure, and is a
    pass-through for a well-behaved one."""
    demo = _fixture_demo()

    def _boom(_demo: Demo) -> list[VerifyCheck]:
        raise RuntimeError("nope")

    checks = runner._safe_verify(_boom, demo)
    assert len(checks) == 1
    assert checks[0].failure_category == "harness"
    assert checks[0].passed is False

    good = [VerifyCheck(name="x", passed=True, reason="ok", failure_category=None)]
    assert runner._safe_verify(lambda _d: good, demo) == good
