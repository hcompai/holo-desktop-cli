"""Demo runner with deterministic post-run verification.

One call = one demo run. For each invocation the runner:

1. Optionally downloads/checks fixtures (delegates to `fixtures.ensure`).
2. Calls `demo.setup()` once for demo-specific staging (copy receipts onto the
   Desktop, etc).
3. Launches every `AppLaunchSpec` in order, then brings `demo.focus_bundle_id`
   frontmost — the agent drives the whole desktop and starts on whatever has
   focus.
4. Runs `demo.task` through `session.Runtime`.
5. Runs the demo's verifier (if registered) BEFORE teardown, while the demo's
   artifacts are still in place.
6. Calls `demo.teardown()`.
7. Writes events.jsonl, task.json, and appends to summary-demos.csv.
"""

from __future__ import annotations

import csv
import json
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from statistics import fmean
from typing import Literal

from holo_desktop.agent_client import runtime_log_path, runtime_log_tail
from holo_desktop.agent_client.event_timings import StepTiming, StepTimingsSummary, render_step_timings
from holo_desktop.killswitch import (
    KILL_SWITCH_ARMED_HINT,
    KILL_SWITCH_UNAVAILABLE_HINT,
    ArmOutcome,
    arm_stop_listener,
    is_interactive_tty,
)
from pydantic import BaseModel, ConfigDict, Field
from rich.console import Console

from expense_report_demo import apps, fixtures
from expense_report_demo.demos.verify import VerifyCheck
from expense_report_demo.holo_kwargs import HoloKwargs
from expense_report_demo.metrics import Metrics, StepStats, read_events
from expense_report_demo.session import Runtime

# Cap the runtime stderr tail echoed on failure so a crash dump can't bury the summary.
_LOG_TAIL_LINES = 20

# DemoHook is the canonical type for per-demo setup/teardown callables; the
# registry stores them in `HOOKS` (see `expense_report_demo.demos.registry`).
DemoHook = Callable[["Demo"], None]
# DemoVerifier reads the post-run world and returns deterministic checks.
DemoVerifier = Callable[["Demo"], list[VerifyCheck]]


class AppLaunchSpec(BaseModel):
    """One pre-launch step. Bundle ids only (no AppleScript name fallback) so we
    fail loud if someone mistypes."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    bundle_id: str = Field(min_length=1, description="e.g. 'com.apple.finder'")
    urls: list[str] | None = Field(description="URLs/paths handed to the app's open delegate, or None")
    isolated_browser_session: bool = Field(description="Chromium-only: spawn a fresh sandboxed profile")


class Demo(BaseModel):
    """A self-contained demo definition. Pydantic-frozen, no defaults — everything explicit."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    slug: str = Field(min_length=1, description="Stable id, used in CLI + output paths")
    title: str = Field(min_length=1, description="One-line human-readable name")
    description: str = Field(min_length=1, description="One-paragraph what this demo proves")
    fixtures_manifest: Path | None = Field(description="manifests/<slug>.toml, or None if no fixtures")
    pre_launch: list[AppLaunchSpec] = Field(min_length=1, description="Apps launched in order before the run")
    focus_bundle_id: str = Field(
        min_length=1, description="Bundle id brought frontmost last; the agent starts focused on it"
    )
    task: str = Field(min_length=1, description="The natural-language task handed to Holo")
    max_steps: int = Field(ge=1, le=500)
    max_time_s: float = Field(ge=1.0, le=3600.0)


DemoOutcome = Literal["ok", "error", "interrupted"]


class DemoRun(BaseModel):
    """One run summary, written verbatim to task.json."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    demo: Demo
    holo_kwargs: HoloKwargs
    run_id: str
    session_id: str | None
    started_at: str
    ended_at: str
    elapsed_s: float
    outcome: DemoOutcome
    error: str | None
    answer: str | None
    verify_checks: list[VerifyCheck] | None
    events_path: str
    metrics: Metrics | None


def run_demo(
    demo: Demo,
    holo_kwargs: HoloKwargs,
    out_root: Path,
    dry_run: bool,
    hooks: tuple[DemoHook, DemoHook] | None,
    verifier: DemoVerifier | None,
    expand_feed: bool,
    profile: bool,
) -> DemoRun:
    """Execute one demo end-to-end. Returns a DemoRun (also persisted to disk).

    `hooks`/`verifier` are injected by the caller (typically from
    `expense_report_demo.demos.registry`) so the runner doesn't depend on the registry —
    keeps the import graph acyclic."""
    if dry_run:
        return _dry_run(demo, holo_kwargs, out_root)

    if demo.fixtures_manifest is not None:
        fixtures.ensure(
            demo.fixtures_manifest,
            dest_root=Path("fixtures") / demo.slug,
            cache_dir=Path("fixtures") / ".cache",
        )

    # Hermetic launch: kill stale instances before staging files, so pre-launch
    # reopens fixtures fresh. A left-open editor would otherwise keep a prior
    # run's document in memory and shadow the newly staged file.
    apps.kill_all([spec.bundle_id for spec in demo.pre_launch])

    setup_fn, teardown_fn = hooks if hooks is not None else (None, None)

    started_at = datetime.now(UTC)
    t0 = time.perf_counter()
    outcome: DemoOutcome = "ok"
    error: str | None = None
    answer: str | None = None
    session_id: str | None = None
    verify_checks: list[VerifyCheck] | None = None
    session_ran = False

    run_id = started_at.strftime("%Y%m%d-%H%M%S")
    events_path = out_root / demo.slug / run_id / "events.jsonl"

    # setup, session, verify, and teardown all live under one try/finally so a
    # failure in setup (Desktop staging) or in the verifier never strands the
    # demo without teardown or a persisted run record.
    try:
        if setup_fn is not None:
            setup_fn(demo)
        with Runtime(holo_kwargs.runtime_config()) as runtime:
            for spec in demo.pre_launch:
                _launch_one(spec)
            apps.activate_app(demo.focus_bundle_id)
            # Armed only around the session, so a double-Esc files a stop that run_turn honors;
            # a stop pressed during setup above is stale and would be ignored.
            kill_switch, arm_outcome = arm_stop_listener(enabled=is_interactive_tty() and not holo_kwargs.fake)
            if arm_outcome is ArmOutcome.UNAVAILABLE:
                print(f"  [run] {KILL_SWITCH_UNAVAILABLE_HINT}", file=sys.stderr)
            elif arm_outcome is ArmOutcome.ARMED:
                print(f"  [run] {KILL_SWITCH_ARMED_HINT}", file=sys.stderr)
            try:
                result = runtime.run_task(
                    task=demo.task,
                    max_steps=holo_kwargs.max_steps,
                    max_time_s=holo_kwargs.max_time_s,
                    events_path=events_path,
                    expand_feed=expand_feed,
                )
            finally:
                if kill_switch is not None:
                    kill_switch.stop()
            session_ran = True
            session_id = result.session_id
            answer = result.answer
            if result.status == "interrupted":
                outcome = "interrupted"
                error = result.error or "stopped by user"
            elif result.status != "completed":
                outcome = "error"
                error = result.error or f"session ended {result.status}"
    except KeyboardInterrupt:
        outcome = "interrupted"
        error = "stopped by user"
    except Exception as exc:
        outcome = "error"
        error = f"{type(exc).__name__}: {exc}"
        print(f"  [run] {demo.slug} ERROR: {error}", file=sys.stderr)
    finally:
        # Grade whenever a session actually ran — a timed-out or failed session may
        # still have updated the ledger/Mail. Skip only when no session ran (setup
        # or runtime spawn failure) or the user interrupted mid-task.
        if session_ran and outcome != "interrupted" and verifier is not None:
            verify_checks = _safe_verify(verifier, demo)
        if teardown_fn is not None:
            try:
                teardown_fn(demo)
            except Exception as exc:
                print(f"  [run] {demo.slug} teardown error: {type(exc).__name__}: {exc}", file=sys.stderr)

    elapsed_s = round(time.perf_counter() - t0, 2)
    ended_at = datetime.now(UTC)
    metrics = Metrics.from_events(read_events(events_path)) if events_path.exists() else None

    run = DemoRun(
        demo=demo,
        holo_kwargs=holo_kwargs,
        run_id=run_id,
        session_id=session_id,
        started_at=started_at.isoformat(),
        ended_at=ended_at.isoformat(),
        elapsed_s=elapsed_s,
        outcome=outcome,
        error=error,
        answer=answer,
        verify_checks=verify_checks,
        events_path=str(events_path),
        metrics=metrics,
    )
    _persist(run, out_root)
    _print_summary(run)
    if profile and run.metrics is not None:
        print_step_timings(run.metrics)
    return run


def _safe_verify(verifier: DemoVerifier, demo: Demo) -> list[VerifyCheck]:
    """Run the verifier, converting any exception into a harness failure so a
    crashing check never aborts teardown or run persistence."""
    try:
        return verifier(demo)
    except Exception as exc:
        return [
            VerifyCheck(
                name="verifier",
                passed=False,
                reason=f"verifier raised: {type(exc).__name__}: {exc}",
                failure_category="harness",
            )
        ]


def _launch_one(spec: AppLaunchSpec) -> None:
    """Launch one app and wait until its process exists."""
    apps.launch_app(
        spec.bundle_id,
        urls=spec.urls or [],
        new_instance=spec.isolated_browser_session,
        extra_args=[],
    )
    apps.wait_for_app(spec.bundle_id)


def _verify_summary(checks: list[VerifyCheck] | None) -> str:
    if checks is None:
        return ""
    return f"{sum(1 for c in checks if c.passed)}/{len(checks)}"


def _persist(run: DemoRun, out_root: Path) -> None:
    """Write task.json next to events.jsonl + append a row to summary-demos.csv."""
    task_path = out_root / run.demo.slug / run.run_id / "task.json"
    task_path.parent.mkdir(parents=True, exist_ok=True)
    task_path.write_text(json.dumps(run.model_dump(mode="json"), indent=2, default=str))

    summary_path = out_root / "summary-demos.csv"
    headers = [
        "demo",
        "run_id",
        "started_at",
        "outcome",
        "verify_pass",
        "n_steps",
        "elapsed_s",
        "llm_median_s",
        "llm_p95_s",
        "answer",
    ]
    m = run.metrics
    row = {
        "demo": run.demo.slug,
        "run_id": run.run_id,
        "started_at": run.started_at,
        "outcome": run.outcome,
        "verify_pass": _verify_summary(run.verify_checks),
        "n_steps": m.n_steps if m else 0,
        "elapsed_s": run.elapsed_s,
        "llm_median_s": (m.llm.median if (m and m.llm) else ""),
        "llm_p95_s": (m.llm.p95 if (m and m.llm) else ""),
        "answer": (run.answer or "")[:120].replace("\n", " "),
    }
    write_header = not summary_path.exists()
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    with summary_path.open("a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        if write_header:
            writer.writeheader()
        writer.writerow(row)


def _print_summary(run: DemoRun) -> None:
    m = run.metrics
    llm_p50 = m.llm.median if (m and m.llm) else 0.0
    verify = _verify_summary(run.verify_checks)
    print(
        f"  [{run.demo.slug:24}] {run.outcome:11} "
        f"verify={verify or '-':5} steps={(m.n_steps if m else 0):>2} elapsed={run.elapsed_s:>5.1f}s "
        f"llm_p50={llm_p50:>5.2f}s answer={(run.answer or '')[:60]!r}"
    )
    if run.verify_checks:
        for check in run.verify_checks:
            mark = "PASS" if check.passed else "FAIL"
            category = f" [{check.failure_category}]" if check.failure_category else ""
            print(f"    [verify] {mark}{category} {check.name}: {check.reason}")
    if run.outcome != "ok":
        _print_failure_detail(run)


def print_step_timings(metrics: Metrics) -> None:
    """Per-step observe/llm/tool phase table with an averages footer."""
    if not metrics.steps:
        print("  [profile] no step timings recorded (no policy events)")
        return
    render_step_timings(_timings_summary(metrics.steps), Console())


def _timings_summary(steps: list[StepStats]) -> StepTimingsSummary:
    """Adapt demo StepStats into the shared renderer's typed summary."""
    return StepTimingsSummary(
        steps=tuple(
            StepTiming(
                step_idx=s.step,
                tool_name=s.tool,
                observe_s=s.observation_s,
                llm_s=s.llm_s,
                tool_s=s.tool_s,
                failed=False,
            )
            for s in steps
        ),
        avg_observe_s=_mean([s.observation_s for s in steps]),
        avg_llm_s=_mean([s.llm_s for s in steps]),
        avg_tool_s=_mean([s.tool_s for s in steps]),
        avg_step_s=_mean([(s.observation_s or 0.0) + s.llm_s + (s.tool_s or 0.0) for s in steps]),
        steps_timed=len(steps),
    )


def _mean(values: list[float | None]) -> float | None:
    present = [v for v in values if v is not None]
    return round(fmean(present), 3) if present else None


def _print_failure_detail(run: DemoRun) -> None:
    """On a non-ok run, echo the error and the runtime's stderr tail so the cause isn't buried."""
    if run.error:
        print(f"    [error] {run.error}", file=sys.stderr)
    log_path = runtime_log_path(run.holo_kwargs.port)
    print(f"    [error] runtime log: {log_path}", file=sys.stderr)
    tail = runtime_log_tail(run.holo_kwargs.port)
    for line in tail.splitlines()[-_LOG_TAIL_LINES:]:
        print(f"    [runtime] {line}", file=sys.stderr)


def _dry_run(
    demo: Demo,
    holo_kwargs: HoloKwargs,
    out_root: Path,
) -> DemoRun:
    print(f"  [dry-run] {demo.slug}: would launch {[s.bundle_id for s in demo.pre_launch]}")
    print(f"  [dry-run] {demo.slug}: would focus {demo.focus_bundle_id!r}")
    print(f"  [dry-run] {demo.slug}: task = {demo.task!r}")
    print(f"  [dry-run] {demo.slug}: holo_kwargs = {holo_kwargs.model_dump(exclude_none=True)}")
    print(f"  [dry-run] {demo.slug}: output would go to {out_root / demo.slug}")
    now = datetime.now(UTC).isoformat()
    return DemoRun(
        demo=demo,
        holo_kwargs=holo_kwargs,
        run_id="dry-run",
        session_id=None,
        started_at=now,
        ended_at=now,
        elapsed_s=0.0,
        outcome="ok",
        error=None,
        answer=None,
        verify_checks=None,
        events_path="",
        metrics=None,
    )
