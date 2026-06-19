"""Tests for deriving profile timings from raw runtime event logs."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from holo_desktop.agent_client.event_timings import extract_step_timings, find_session_event_log


def _record(ts: datetime, kind: str, **event: object) -> str:
    return json.dumps({"ts": ts.isoformat(), "event": {"kind": kind, **event}})


def _touch_log(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")
    return path


def test_find_session_event_log_prefers_the_matching_session(tmp_path: Path) -> None:
    match = _touch_log(tmp_path / "session-abc" / "events.jsonl")
    _touch_log(tmp_path / "session-xyz" / "events.jsonl")
    assert find_session_event_log(tmp_path, "abc") == match


def test_find_session_event_log_returns_sole_log_when_unattributable(tmp_path: Path) -> None:
    only = _touch_log(tmp_path / "run-1" / "events.jsonl")
    assert find_session_event_log(tmp_path, "no-such-session") == only


def test_find_session_event_log_refuses_wrong_log_when_ambiguous(tmp_path: Path) -> None:
    # Several runs and none carry this session id: showing another run's timings would mislead.
    _touch_log(tmp_path / "run-1" / "events.jsonl")
    _touch_log(tmp_path / "run-2" / "events.jsonl")
    assert find_session_event_log(tmp_path, "no-such-session") is None


def test_extract_step_timings_derives_phase_durations_from_event_records(tmp_path: Path) -> None:
    start = datetime(2026, 6, 12, 12, 0, tzinfo=UTC)
    event_log = tmp_path / "events.jsonl"
    event_log.write_text(
        "\n".join(
            [
                _record(start, "message_event", caller_id="user", content=["do it"]),
                _record(start + timedelta(seconds=1), "observation_event"),
                _record(
                    start + timedelta(seconds=3),
                    "policy_event",
                    tool_reqs=[{"tool_name": "click_desktop"}],
                ),
                _record(
                    start + timedelta(seconds=7),
                    "tool_result",
                    tool_req={"tool_name": "click_desktop"},
                ),
            ]
        ),
        encoding="utf-8",
    )

    summary = extract_step_timings(event_log)

    assert summary is not None
    assert summary.steps_timed == 1
    assert summary.avg_observe_s == 1.0
    assert summary.avg_llm_s == 2.0
    assert summary.avg_tool_s == 4.0
    assert summary.avg_step_s == 7.0
    (step,) = summary.steps
    assert step.step_idx == 1
    assert step.tool_name == "click_desktop"
    assert step.observe_s == 1.0
    assert step.llm_s == 2.0
    assert step.tool_s == 4.0
    assert step.failed is False


def test_extract_step_timings_includes_pending_final_step(tmp_path: Path) -> None:
    start = datetime(2026, 6, 12, 12, 0, tzinfo=UTC)
    event_log = tmp_path / "events.jsonl"
    event_log.write_text(
        "\n".join(
            [
                _record(start, "observation_event"),
                _record(start + timedelta(seconds=2), "policy_event"),
            ]
        ),
        encoding="utf-8",
    )

    summary = extract_step_timings(event_log)

    assert summary is not None
    assert summary.steps_timed == 1
    (step,) = summary.steps
    assert step.step_idx == 1
    assert step.tool_name is None
    assert step.observe_s == 0.0
    assert step.llm_s == 2.0
    assert step.tool_s is None
    assert step.failed is False


def test_extract_step_timings_ignores_legacy_step_timings_event(tmp_path: Path) -> None:
    event_log = tmp_path / "events.jsonl"
    event_log.write_text(
        json.dumps({"ts": "2026-06-12T12:00:00+00:00", "event": {"kind": "step_timings", "steps": []}}),
        encoding="utf-8",
    )

    assert extract_step_timings(event_log) is None
