"""Behavioural tests for shared metrics over runtime-shaped event records.

These build the same wire records `session.Runtime.run_task` persists
(`type` + `data.kind` + `timestamp`), then run `Metrics.from_events` and
`read_events` against them.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from pydantic import JsonValue

from expense_report_demo.metrics import EventRecord, Metrics, Stat, read_events


def _record(kind: str | None, ts: datetime, **extra: JsonValue) -> EventRecord:
    if kind is None:
        return EventRecord(type="AgentStartedEvent", timestamp=ts, data={})
    return EventRecord(type="AgentEvent", timestamp=ts, data={"kind": kind, **extra})


def _policy(ts: datetime, tool: str) -> EventRecord:
    return _record("policy_event", ts, tool_reqs=[{"tool_name": tool, "args": {}, "id": "x"}])


def test_stat_of_empty_is_none() -> None:
    assert Stat.of([]) is None


def test_stat_basic_distribution() -> None:
    s = Stat.of([1.0, 2.0, 3.0, 4.0, 5.0])
    assert s is not None
    assert s.n == 5
    assert s.median == 3.0
    assert s.max == 5.0
    assert s.total == 15.0
    # p95_idx = int(0.95 * 5) = 4 → values[4] = 5.0
    assert s.p95 == 5.0


def test_metrics_from_events_three_steps() -> None:
    """Three policy events with tool results + observations between them."""
    t0 = datetime.now(UTC)
    events = [
        _record("observation_event", t0),
        _policy(t0 + timedelta(seconds=1.0), "click"),
        _record("tool_result", t0 + timedelta(seconds=1.5)),
        _record("observation_event", t0 + timedelta(seconds=2.0)),
        _policy(t0 + timedelta(seconds=3.0), "click"),
        _record("tool_result", t0 + timedelta(seconds=3.4)),
        _record("observation_event", t0 + timedelta(seconds=3.8)),
        _policy(t0 + timedelta(seconds=5.0), "answer"),
        _record("tool_result", t0 + timedelta(seconds=5.2)),
    ]
    m = Metrics.from_events(events)

    assert m.n_steps == 3
    assert m.elapsed_s == 5.2
    assert m.llm is not None and m.llm.n == 3
    assert m.tool is not None and m.tool.n == 3
    assert "click" in m.by_tool
    assert "answer" in m.by_tool
    assert m.by_tool["click"].n == 2
    assert m.steps[0].llm_s == 1.0
    assert m.steps[0].tool_s == 0.5
    assert m.steps[0].observation_s == 0.5
    assert "observation_event->policy_event" in m.transitions


def test_metrics_accepts_tool_result_event_kind() -> None:
    """Both flattened spellings of the tool-result kind close a step."""
    t0 = datetime.now(UTC)
    events = [
        _policy(t0, "click"),
        _record("tool_result_event", t0 + timedelta(seconds=0.7)),
    ]
    m = Metrics.from_events(events)
    assert m.n_steps == 1
    assert m.steps[0].tool_s == 0.7


def test_metrics_from_empty_events() -> None:
    m = Metrics.from_events([])
    assert m.n_steps == 0
    assert m.elapsed_s == 0.0
    assert m.llm is None
    assert m.by_tool == {}


def test_lifecycle_events_use_wire_type_as_transition_label() -> None:
    t0 = datetime.now(UTC)
    events = [
        _record(None, t0),
        _record("observation_event", t0 + timedelta(seconds=0.3)),
    ]
    m = Metrics.from_events(events)
    assert "AgentStartedEvent->observation_event" in m.transitions


def test_read_events_roundtrip(tmp_path: Path) -> None:
    """Write real records as JSONL, read them back via read_events, compare."""
    t0 = datetime.now(UTC)
    original = [
        _record("observation_event", t0),
        _policy(t0 + timedelta(seconds=0.5), "click"),
    ]
    log = tmp_path / "events.jsonl"
    log.write_text("\n".join(r.model_dump_json() for r in original))

    parsed = read_events(log)
    assert len(parsed) == 2
    assert parsed[0].kind == "observation_event"
    assert parsed[1].kind == "policy_event"
    assert parsed[1].first_tool_name() == "click"


def test_read_events_skips_malformed_lines(tmp_path: Path) -> None:
    """Bad JSONL lines are silently skipped (contextlib.suppress in source)."""
    log = tmp_path / "events.jsonl"
    log.write_text("not json\n{}\n   \n")
    parsed = read_events(log)
    assert parsed == []


def test_read_events_missing_file_returns_empty(tmp_path: Path) -> None:
    assert read_events(tmp_path / "nope.jsonl") == []
