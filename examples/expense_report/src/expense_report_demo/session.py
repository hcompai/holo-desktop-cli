"""Sync session layer over the hai-agent-runtime agent API.

`Runtime` owns one daemon for its context (spawned fresh, or attached when one
already listens on the port) and runs any number of sequential tasks against
it. Each task streams its `TrajectoryEvent`s into a caller-chosen JSONL file,
so per-run logs live next to the run's `task.json` regardless of the binary's
own `~/.holo/runs` layout.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from types import TracebackType
from typing import Literal

from agp_types import TrajectoryEvent, TrajectoryStatus
from hai_agents.local import LocalRuntime
from holo_desktop.agent_client import AgentApiClient, SpawnConfig, ensure_local_runtime
from holo_desktop.agent_client.events import is_policy_event
from holo_desktop.agent_client.session_runner import Session, TurnOutcome, run_turn
from holo_desktop.cli.bootstrap import load_holo_env, require_api_key
from holo_desktop.settings import load_holo_settings
from holo_desktop.terminal import LiveFeed
from pydantic import BaseModel, ConfigDict, Field
from rich.console import Console

TaskStatus = Literal["completed", "failed", "timed_out", "interrupted"]

_TERMINAL_STATUS: dict[TrajectoryStatus, TaskStatus] = {
    TrajectoryStatus.COMPLETED: "completed",
    # IDLE = answered and awaiting the next turn; for a one-shot task that is completion.
    TrajectoryStatus.IDLE: "completed",
    TrajectoryStatus.FAILED: "failed",
    TrajectoryStatus.TIMED_OUT: "timed_out",
    TrajectoryStatus.INTERRUPTED: "interrupted",
}


class RuntimeConfig(BaseModel):
    """Spawn-time knobs forwarded to the binary; per-task knobs live on `run_task`."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    port: int = Field(ge=1, le=65535)
    model: str | None
    base_url: str | None
    fake: bool


class TaskResult(BaseModel):
    """Outcome of one session run, derived from the event stream's final projection."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    session_id: str
    answer: str | None
    status: TaskStatus
    error: str | None
    n_steps: int = Field(ge=0, description="Number of policy events (LLM decisions) observed")


class Runtime:
    """Sync context manager around one reachable hai-agent-runtime daemon."""

    def __init__(self, config: RuntimeConfig) -> None:
        self._config = config
        self._runtime: LocalRuntime | None = None

    def __enter__(self) -> Runtime:
        # Per-request HTTP logs are implementation detail, not run output.
        logging.getLogger("httpx").setLevel(logging.WARNING)
        load_holo_env()
        settings = load_holo_settings()
        if not self._config.fake:
            require_api_key(explicit_base_url=self._config.base_url, settings=settings)
        self._runtime = ensure_local_runtime(
            SpawnConfig(
                port=self._config.port,
                model=self._config.model,
                base_url=self._config.base_url,
                fake=self._config.fake,
            ),
            settings=settings,
        )
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        runtime = self._runtime
        self._runtime = None
        if runtime is not None and runtime.owned:
            runtime.shutdown()

    @property
    def log_path(self) -> Path | None:
        """Runtime stderr log, when the SDK owns or discovered one."""
        return self._runtime.log_path if self._runtime is not None else None

    def run_task(
        self, *, task: str, max_steps: int, max_time_s: float, events_path: Path, expand_feed: bool
    ) -> TaskResult:
        """Run one session to end-of-turn, persisting every event to `events_path`."""
        runtime = self._runtime
        if runtime is None:
            raise RuntimeError("Runtime.run_task called outside the Runtime context")
        return asyncio.run(
            _drive(
                runtime,
                task=task,
                max_steps=max_steps,
                max_time_s=max_time_s,
                events_path=events_path,
                expand_feed=expand_feed,
            )
        )


def _project_result(outcome: TurnOutcome, *, n_steps: int) -> TaskResult:
    """Project a finished turn into a TaskResult; a non-terminal status is a runtime contract breach.

    ``session_id`` comes straight off the outcome, which captured it before any stop-driven reset, so
    an interrupted run keeps the id it ran against. It is "" only when a stop won before any session
    was created — a genuinely sessionless outcome.
    """
    if outcome.status is None or outcome.status not in _TERMINAL_STATUS:
        raise RuntimeError(f"session {outcome.session_id!r} ended in non-terminal status {outcome.status!r}")
    return TaskResult(
        session_id=outcome.session_id or "",
        answer=outcome.answer or None,
        status=_TERMINAL_STATUS[outcome.status],
        error=outcome.error,
        n_steps=n_steps,
    )


async def _drive(
    runtime: LocalRuntime,
    *,
    task: str,
    max_steps: int,
    max_time_s: float,
    events_path: Path,
    expand_feed: bool,
) -> TaskResult:
    events_path.parent.mkdir(parents=True, exist_ok=True)
    feed = LiveFeed(Console(stderr=True), expand=expand_feed)
    n_steps = 0
    async with AgentApiClient(runtime) as client:
        session = Session()
        with events_path.open("w", encoding="utf-8") as sink:

            async def on_event(event: TrajectoryEvent) -> None:
                nonlocal n_steps
                sink.write(event.model_dump_json() + "\n")
                if is_policy_event(event):
                    n_steps += 1
                feed.handle(event)

            try:
                outcome = await run_turn(
                    client, session, task, max_steps=max_steps, max_time_s=max_time_s, on_event=on_event
                )
            finally:
                feed.close()

    return _project_result(outcome, n_steps=n_steps)
