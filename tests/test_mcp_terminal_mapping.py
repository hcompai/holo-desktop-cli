"""Behavioural tests for `holo_desktop` MCP terminal-status handling."""

from __future__ import annotations

import asyncio
import importlib
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from agp_types import TrajectoryEvent, TrajectoryStatus

from holo_desktop.agent_client.session_runner import Session
from holo_desktop.cli.mcp import Lifespan, holo_desktop

mcp_mod = importlib.import_module("holo_desktop.cli.mcp")

SESSION_ID = "agent-api-session"


@dataclass
class FakeStream:
    status: TrajectoryStatus
    answer: str | None = None
    error: str | None = None
    to_yield: list[TrajectoryEvent] = field(default_factory=list)
    next_index: int = 0

    async def events(self) -> AsyncIterator[TrajectoryEvent]:
        self.next_index += len(self.to_yield)
        for event in self.to_yield:
            yield event


@dataclass
class FakeApiClient:
    outcome: FakeStream
    cancelled: list[str] = field(default_factory=list)

    async def create_session(self, request: object) -> str:
        return SESSION_ID

    async def send_message(self, session_id: str, text: str) -> None:
        pass

    def stream(self, session_id: str, *, from_index: int = 0) -> FakeStream:
        return self.outcome

    async def cancel(self, session_id: str) -> None:
        self.cancelled.append(session_id)

    async def aclose(self) -> None:
        pass


@dataclass
class FakeMcpContext:
    outcome: FakeStream
    infos: list[str] = field(default_factory=list)
    progress: list[tuple[float, str]] = field(default_factory=list)

    @property
    def request_context(self) -> object:
        return SimpleNamespace(lifespan_context=Lifespan(client=FakeApiClient(self.outcome), daemon=None))  # type: ignore[arg-type]

    async def info(self, line: str) -> None:
        self.infos.append(line)

    async def report_progress(self, *, progress: float, message: str) -> None:
        self.progress.append((progress, message))


def test_timed_out_is_not_reported_as_successful_tool_result() -> None:
    ctx = FakeMcpContext(FakeStream(status=TrajectoryStatus.TIMED_OUT, error="budget exhausted"))

    with pytest.raises(RuntimeError, match="budget exhausted"):
        asyncio.run(holo_desktop("do the thing", ctx))  # type: ignore[arg-type]


def test_host_request_cancellation_cancels_active_agent_api_session() -> None:
    event = TrajectoryEvent(
        type="AgentEvent",
        data={"kind": "policy_event", "content": "thinking"},
        timestamp=datetime.now(UTC),
    )
    client = FakeApiClient(FakeStream(status=TrajectoryStatus.COMPLETED, to_yield=[event]))
    state = Lifespan(client=client, daemon=None)  # type: ignore[arg-type]

    async def cancelled_info(line: str) -> None:
        raise asyncio.CancelledError

    ctx = SimpleNamespace(
        request_context=SimpleNamespace(lifespan_context=state),
        info=cancelled_info,
        report_progress=lambda **kwargs: None,
    )

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(holo_desktop("do the thing", ctx))  # type: ignore[arg-type]

    assert client.cancelled == [SESSION_ID]
    assert state.active_session is None


def test_lifespan_shutdown_cancels_active_agent_api_sessions() -> None:
    client = FakeApiClient(FakeStream(status=TrajectoryStatus.COMPLETED))
    active = Session(session_id=SESSION_ID, next_index=4)
    state = Lifespan(client=client, daemon=None)  # type: ignore[arg-type]
    state.active_session = active

    asyncio.run(mcp_mod._cancel_active_sessions_best_effort(state))

    assert client.cancelled == [SESSION_ID]
    assert active.session_id is None
    assert state.active_session is None
