"""Behavioural tests for `--profile` step-timing rendering.

Builds a `Metrics` from runtime-shaped wire records (the same shape
`session.Runtime.run_task` persists), then asserts the rendered table carries
one row per step plus an `avg` footer — mirroring `holo run --profile`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import JsonValue

from expense_report_demo.demos.runner import print_step_timings
from expense_report_demo.metrics import EventRecord, Metrics


def _record(kind: str | None, ts: datetime, **extra: JsonValue) -> EventRecord:
    if kind is None:
        return EventRecord(type="AgentStartedEvent", timestamp=ts, data={})
    return EventRecord(type="AgentEvent", timestamp=ts, data={"kind": kind, **extra})


def _policy(ts: datetime, tool: str) -> EventRecord:
    return _record("policy_event", ts, tool_reqs=[{"tool_name": tool, "args": {}, "id": "x"}])


def _two_step_metrics() -> Metrics:
    t0 = datetime.now(UTC)
    return Metrics.from_events(
        [
            _record("observation_event", t0),
            _policy(t0 + timedelta(seconds=1.0), "click"),
            _record("tool_result", t0 + timedelta(seconds=1.5)),
            _record("observation_event", t0 + timedelta(seconds=2.0)),
            _policy(t0 + timedelta(seconds=3.0), "type_text"),
            _record("tool_result", t0 + timedelta(seconds=3.4)),
        ]
    )


def test_renders_one_row_per_step_with_tools(capsys: pytest.CaptureFixture[str]) -> None:
    print_step_timings(_two_step_metrics())
    out = capsys.readouterr().out
    assert "step timings" in out
    assert "click" in out
    assert "type_text" in out
    assert "avg" in out


def test_empty_metrics_reports_no_timings(capsys: pytest.CaptureFixture[str]) -> None:
    print_step_timings(Metrics.from_events([]))
    out = capsys.readouterr().out
    assert "no step timings recorded" in out
    assert "step timings (s)" not in out
