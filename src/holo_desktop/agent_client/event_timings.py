"""Derive profile timing summaries from runtime ``events.jsonl`` traces."""

from __future__ import annotations

import json
import statistics
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from agent_interface.agent_events import (
    AgentEventData,
    ErrorEvent,
    ObservationEvent,
    PolicyEvent,
    ToolResultEvent,
)
from pydantic import BaseModel, ConfigDict
from rich.console import Console
from rich.table import Table

from holo_desktop.agent_client.events import parse_agent_event_data

DEFAULT_RUNS_DIR = Path("~/.holo/runs").expanduser()
# Error origins that close a step as a failed tool execution.
_TOOL_ERROR_ORIGINS = frozenset({"tool", "tool_validation"})


@dataclass
class _StepTiming:
    """Mutable accumulator for one step's phase durations while walking the trace."""

    step_idx: int
    tool_name: str | None = None
    observe_s: float | None = None
    llm_s: float | None = None
    tool_s: float | None = None
    failed: bool = False

    @property
    def total_s(self) -> float:
        return sum(value for value in (self.observe_s, self.llm_s, self.tool_s) if value is not None)


class StepTiming(BaseModel):
    """Per-step phase durations (seconds); ``None`` where a phase was not observed."""

    model_config = ConfigDict(frozen=True)
    step_idx: int
    tool_name: str | None
    observe_s: float | None
    llm_s: float | None
    tool_s: float | None
    failed: bool


class StepTimingsSummary(BaseModel):
    """Per-step timings plus phase averages across one session's trace."""

    model_config = ConfigDict(frozen=True)
    steps: tuple[StepTiming, ...]
    avg_observe_s: float | None
    avg_llm_s: float | None
    avg_tool_s: float | None
    avg_step_s: float | None
    steps_timed: int


def find_session_event_log(runs_dir: Path | None, session_id: str) -> Path | None:
    """``events.jsonl`` for ``session_id``; only falls back to the sole log when attribution is unambiguous."""
    root = DEFAULT_RUNS_DIR if runs_dir is None else runs_dir.expanduser()
    if not root.exists():
        return None
    candidates = [path for path in root.rglob("events.jsonl") if path.is_file()]
    if not candidates:
        return None
    if session_id:
        matches = [path for path in candidates if session_id in str(path)]
        if matches:
            return max(matches, key=lambda path: path.stat().st_mtime)
        # Multiple runs and none attributable to this session: refuse to show another run's timings.
        if len(candidates) > 1:
            return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def extract_step_timings(event_log: Path | None) -> StepTimingsSummary | None:
    """Compute per-step profile timings from raw agent-event timestamp deltas."""
    steps = _derive_steps(_load_records(event_log))
    if not steps:
        return None
    return StepTimingsSummary(
        steps=tuple(
            StepTiming(
                step_idx=step.step_idx,
                tool_name=step.tool_name,
                observe_s=step.observe_s,
                llm_s=step.llm_s,
                tool_s=step.tool_s,
                failed=step.failed,
            )
            for step in steps
        ),
        avg_observe_s=_mean(step.observe_s for step in steps),
        avg_llm_s=_mean(step.llm_s for step in steps),
        avg_tool_s=_mean(step.tool_s for step in steps),
        avg_step_s=_mean(step.total_s for step in steps),
        steps_timed=len(steps),
    )


def render_step_timings(summary: StepTimingsSummary, console: Console) -> None:
    """Render a timing summary as a per-step phase table plus averages."""
    table = Table(title="step timings (s)", title_justify="left", header_style="bold")
    for column in ("step", "tool", "observe", "llm", "tool exec", "total"):
        table.add_column(column, justify="right" if column != "tool" else "left")
    for step in summary.steps:
        total = sum(value or 0.0 for value in (step.observe_s, step.llm_s, step.tool_s))
        table.add_row(
            str(step.step_idx),
            step.tool_name or "--",
            _fmt_s(step.observe_s),
            _fmt_s(step.llm_s),
            _fmt_s(step.tool_s),
            f"{total:.2f}",
        )
    table.add_section()
    table.add_row(
        "avg",
        "",
        _fmt_s(summary.avg_observe_s),
        _fmt_s(summary.avg_llm_s),
        _fmt_s(summary.avg_tool_s),
        _fmt_s(summary.avg_step_s),
        style="bold",
    )
    console.print(table)


def _load_records(event_log: Path | None) -> list[tuple[datetime, AgentEventData]]:
    if event_log is None or not event_log.exists():
        return []
    records: list[tuple[datetime, AgentEventData]] = []
    for line in event_log.read_text(encoding="utf-8").splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(record, dict):
            continue
        raw_event = record.get("event")
        if not isinstance(raw_event, dict):
            continue
        ts = _parse_ts(record.get("ts"))
        if ts is None:
            continue
        parsed = parse_agent_event_data(raw_event)
        if parsed is None:
            continue
        records.append((ts, parsed))
    return records


def _derive_steps(records: list[tuple[datetime, AgentEventData]]) -> list[_StepTiming]:
    steps: list[_StepTiming] = []
    first_event_at: datetime | None = None
    prev_step_end_at: datetime | None = None
    observe_at: datetime | None = None
    llm_at: datetime | None = None
    pending: _StepTiming | None = None

    for ts, event in records:
        if first_event_at is None:
            first_event_at = ts
        match event:
            case ObservationEvent():
                if pending is not None:
                    steps.append(pending)
                baseline = prev_step_end_at or first_event_at or ts
                pending = _StepTiming(step_idx=len(steps) + 1, observe_s=_seconds(ts - baseline))
                observe_at = ts
                llm_at = None
            case PolicyEvent():
                if pending is None:
                    pending = _StepTiming(step_idx=len(steps) + 1, observe_s=None)
                    observe_at = None
                    llm_at = None
                boundary = observe_at or prev_step_end_at or first_event_at
                if boundary is not None:
                    pending.llm_s = _seconds(ts - boundary)
                pending.tool_name = _first_tool_name(event)
                llm_at = ts
            case ToolResultEvent() if pending is not None:
                _close_step(steps, pending, ts=ts, llm_at=llm_at, failed=False)
                pending = None
                prev_step_end_at = ts
                observe_at = None
                llm_at = None
            case ErrorEvent() if pending is not None and event.origin in _TOOL_ERROR_ORIGINS:
                _close_step(steps, pending, ts=ts, llm_at=llm_at, failed=True)
                pending = None
                prev_step_end_at = ts
                observe_at = None
                llm_at = None
    if pending is not None:
        steps.append(pending)
    return steps


def _close_step(
    steps: list[_StepTiming],
    pending: _StepTiming,
    *,
    ts: datetime,
    llm_at: datetime | None,
    failed: bool,
) -> None:
    if llm_at is not None:
        pending.tool_s = _seconds(ts - llm_at)
    pending.failed = failed
    steps.append(pending)


def _first_tool_name(event: PolicyEvent) -> str | None:
    return event.tool_reqs[0].tool_name if event.tool_reqs else None


def _parse_ts(raw: object) -> datetime | None:
    if not isinstance(raw, str):
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _mean(values: Iterable[float | None]) -> float | None:
    present = [value for value in values if value is not None]
    if not present:
        return None
    return round(statistics.fmean(present), 3)


def _seconds(delta: timedelta) -> float:
    # Clamp: out-of-order or clock-skewed timestamps must not yield a negative phase duration.
    return round(max(0.0, delta.total_seconds()), 3)


def _fmt_s(value: float | None) -> str:
    return f"{value:.2f}" if value is not None else "--"
