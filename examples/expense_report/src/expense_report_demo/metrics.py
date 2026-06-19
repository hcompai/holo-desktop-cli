"""Post-hoc metrics over a run's persisted `TrajectoryEvent` JSONL.

Each line is one wire event: `{"type": ..., "data": {...}, "timestamp": ...}`,
with agent activity flattened into `data["kind"]` (observation_event /
policy_event / tool_result / ...). Steps anchor at policy events (one LLM
decision each). For each step we measure:
  llm_s          = wallclock from the preceding event (typically the
                   observation) to the policy event
  tool_s         = policy event -> next tool result
  observation_s  = tool result -> next observation (next step's screenshot)
"""

from __future__ import annotations

import contextlib
from collections import defaultdict
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path
from statistics import median

from pydantic import BaseModel, ConfigDict, JsonValue, field_validator

_KIND_OBSERVATION = "observation_event"
_KIND_POLICY = "policy_event"
# The wire flattens the runtime's tool-result event under either name
# depending on the producer; treat both as the same step boundary.
_TOOL_RESULT_KINDS = frozenset({"tool_result", "tool_result_event"})


class EventRecord(BaseModel):
    """One persisted wire event; `data` is the flattened agent-event payload."""

    model_config = ConfigDict(extra="ignore", frozen=True)
    type: str
    timestamp: datetime
    data: JsonValue

    @field_validator("timestamp")
    @classmethod
    def _to_utc(cls, value: datetime) -> datetime:
        # Producers mix UTC-aware (`...Z`) and naive timestamps; naive ones are
        # system-local wall clock. astimezone normalizes both to UTC so duration
        # math never crosses a naive/aware boundary.
        return value.astimezone(UTC)

    @property
    def kind(self) -> str | None:
        if isinstance(self.data, dict):
            kind = self.data.get("kind")
            return kind if isinstance(kind, str) else None
        return None

    @property
    def label(self) -> str:
        """`data.kind` when present, else the wire type (lifecycle events)."""
        return self.kind or self.type

    def first_tool_name(self) -> str | None:
        if not isinstance(self.data, dict):
            return None
        reqs = self.data.get("tool_reqs")
        if not isinstance(reqs, list) or not reqs:
            return None
        first = reqs[0]
        if not isinstance(first, dict):
            return None
        name = first.get("tool_name")
        return name if isinstance(name, str) else None


class Stat(BaseModel):
    """Distribution summary for a numeric series, all rounded to 3 dp."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    n: int
    median: float
    p95: float
    max: float
    total: float

    @classmethod
    def of(cls, values: list[float]) -> Stat | None:
        if not values:
            return None
        sorted_v = sorted(values)
        p95_idx = max(0, min(len(values) - 1, int(0.95 * len(values))))
        return cls(
            n=len(values),
            median=round(median(values), 3),
            p95=round(sorted_v[p95_idx], 3),
            max=round(max(values), 3),
            total=round(sum(values), 3),
        )


class StepStats(BaseModel):
    """One row per LLM decision: latency split into phases."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    step: int
    llm_s: float
    tool_s: float | None
    observation_s: float | None
    tool: str | None


class Metrics(BaseModel):
    """Single source of truth for per-run metrics derived from the event log."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    n_steps: int
    elapsed_s: float
    llm: Stat | None
    tool: Stat | None
    observation: Stat | None
    by_tool: dict[str, Stat]
    steps: list[StepStats]
    transitions: dict[str, Stat]

    @classmethod
    def from_events(cls, events: list[EventRecord]) -> Metrics:
        rows: list[StepStats] = []
        by_tool: dict[str, list[float]] = defaultdict(list)

        for i, record in enumerate(events):
            if record.kind != _KIND_POLICY:
                continue
            llm_s = (record.timestamp - events[i - 1].timestamp).total_seconds() if i > 0 else 0.0
            tool_s: float | None = None
            tool_name = record.first_tool_name()
            observation_s: float | None = None
            last_tool_ts: datetime | None = None
            for j in range(i + 1, len(events)):
                following = events[j]
                if following.kind == _KIND_POLICY:
                    break
                if following.kind in _TOOL_RESULT_KINDS and tool_s is None:
                    tool_s = (following.timestamp - record.timestamp).total_seconds()
                    last_tool_ts = following.timestamp
                    if tool_name is not None:
                        by_tool[tool_name].append(tool_s)
                elif following.kind == _KIND_OBSERVATION and observation_s is None and last_tool_ts is not None:
                    observation_s = (following.timestamp - last_tool_ts).total_seconds()
            rows.append(
                StepStats(
                    step=len(rows) + 1,
                    llm_s=round(llm_s, 3),
                    tool_s=round(tool_s, 3) if tool_s is not None else None,
                    observation_s=round(observation_s, 3) if observation_s is not None else None,
                    tool=tool_name,
                )
            )

        transitions: dict[str, list[float]] = defaultdict(list)
        for prev, curr in pairwise(events):
            transitions[f"{prev.label}->{curr.label}"].append((curr.timestamp - prev.timestamp).total_seconds())

        return cls(
            n_steps=len(rows),
            elapsed_s=round((events[-1].timestamp - events[0].timestamp).total_seconds(), 2)
            if len(events) >= 2
            else 0.0,
            llm=Stat.of([s.llm_s for s in rows]),
            tool=Stat.of([s.tool_s for s in rows if s.tool_s is not None]),
            observation=Stat.of([s.observation_s for s in rows if s.observation_s is not None]),
            by_tool={name: stat for name, samples in sorted(by_tool.items()) if (stat := Stat.of(samples))},
            steps=rows,
            transitions={k: stat for k, samples in sorted(transitions.items()) if (stat := Stat.of(samples))},
        )


def read_events(path: Path) -> list[EventRecord]:
    """Parse a JSONL event log persisted by `session.Runtime.run_task`."""
    if not path.exists():
        return []
    out: list[EventRecord] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        with contextlib.suppress(Exception):
            out.append(EventRecord.model_validate_json(line))
    return out
