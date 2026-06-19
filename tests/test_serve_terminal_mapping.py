"""Behavioural tests for A2A terminal-status projection in `holo serve`."""

from __future__ import annotations

import asyncio
import importlib
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import pytest
from a2a.types import TaskArtifactUpdateEvent, TaskState, TaskStatusUpdateEvent
from agent_interface.specs.session import SessionRequest
from agp_types import TrajectoryEvent, TrajectoryStatus

from holo_desktop.agent_client.session_runner import Session, TurnOutcome
from holo_desktop.settings import load_holo_settings

serve_mod = importlib.import_module("holo_desktop.cli.serve")


@dataclass
class RecordingQueue:
    events: list[Any] = field(default_factory=list)

    async def enqueue_event(self, event: Any) -> None:
        self.events.append(event)


def test_empty_context_id_is_stable_so_cancel_can_resolve_the_session() -> None:
    # A fresh-per-call id would leave cancel unable to find the in-flight turn's Session.
    first = serve_mod._safe_context_id("")
    second = serve_mod._safe_context_id("   ")
    assert first == second == serve_mod._ANONYMOUS_CONTEXT_ID


def test_idle_turn_with_answer_completes_a2a_task(monkeypatch) -> None:
    async def fake_run_turn(*args: Any, **kwargs: Any) -> TurnOutcome:
        return TurnOutcome(status=TrajectoryStatus.IDLE, answer="all done", error=None, session_id="agent-session")

    monkeypatch.setattr(serve_mod, "run_turn", fake_run_turn)
    executor = serve_mod.HoloExecutor(model=None, base_url=None, fake=False, settings=load_holo_settings())
    executor._client = object()  # type: ignore[assignment]
    queue = RecordingQueue()

    asyncio.run(
        executor._run_and_stream(
            Session(),
            "do the thing",
            "task-1",
            "ctx-1",
            queue,  # type: ignore[arg-type]
            metadata=None,
        )
    )

    assert any(isinstance(event, TaskArtifactUpdateEvent) for event in queue.events)
    final = queue.events[-1]
    assert isinstance(final, TaskStatusUpdateEvent)
    assert final.status.state == TaskState.TASK_STATE_COMPLETED
    assert final.status.message is not None
    assert final.status.message.parts[0].text == "all done"


@dataclass
class FakeTask:
    id: str
    context_id: str


@dataclass
class FakeRequestContext:
    context_id: str
    current_task: Any = None


@dataclass
class FakeApiClient:
    cancelled: list[str] = field(default_factory=list)

    async def cancel(self, session_id: str) -> None:
        self.cancelled.append(session_id)


def test_cancel_emits_canceled_status_event() -> None:
    executor = serve_mod.HoloExecutor(model=None, base_url=None, fake=False, settings=load_holo_settings())
    executor._client = FakeApiClient()  # type: ignore[assignment]
    executor._sessions["ctx-1"] = Session(session_id="s", next_index=0)
    queue = RecordingQueue()
    ctx = FakeRequestContext(context_id="ctx-1", current_task=FakeTask(id="task-9", context_id="ctx-1"))

    asyncio.run(executor.cancel(ctx, queue))  # type: ignore[arg-type]

    final = queue.events[-1]
    assert isinstance(final, TaskStatusUpdateEvent)
    assert final.status.state == TaskState.TASK_STATE_CANCELED
    assert final.task_id == "task-9"


@dataclass
class FakeExecuteContext:
    context_id: str
    current_task: Any = None
    message: Any = None
    metadata: Any = None

    def get_user_input(self) -> str:
        return "do the thing"


def test_execute_refuses_new_context_when_every_session_is_busy() -> None:
    # All retained sessions hold an in-flight turn: refuse rather than grow _sessions past the cap.
    executor = serve_mod.HoloExecutor(model=None, base_url=None, fake=False, settings=load_holo_settings())
    executor._client = FakeApiClient()  # type: ignore[assignment]
    queue = RecordingQueue()

    async def go() -> None:
        held = []
        for i in range(serve_mod.MAX_RETAINED_SESSIONS):
            session = Session()
            await session.lock.acquire()
            held.append(session)
            executor._sessions[f"busy-{i}"] = session
        ctx = FakeExecuteContext(context_id="new-ctx", current_task=FakeTask(id="task-x", context_id="new-ctx"))
        await executor.execute(ctx, queue)  # type: ignore[arg-type]
        for session in held:
            session.lock.release()

    asyncio.run(go())
    assert len(executor._sessions) == serve_mod.MAX_RETAINED_SESSIONS
    final = queue.events[-1]
    assert isinstance(final, TaskStatusUpdateEvent)
    assert final.status.state == TaskState.TASK_STATE_FAILED
    assert final.status.message is not None
    assert "capacity" in final.status.message.parts[0].text


def test_cancel_resets_agent_api_session_before_next_a2a_turn(monkeypatch) -> None:
    calls: list[tuple[str | None, int]] = []

    async def fake_run_turn(client: object, session: Session, *args: Any, **kwargs: Any) -> TurnOutcome:
        calls.append((session.session_id, session.next_index))
        session.session_id = "fresh-agent-session"
        return TurnOutcome(
            status=TrajectoryStatus.COMPLETED, answer="done", error=None, session_id="fresh-agent-session"
        )

    monkeypatch.setattr(serve_mod, "run_turn", fake_run_turn)
    executor = serve_mod.HoloExecutor(model=None, base_url=None, fake=False, settings=load_holo_settings())
    client = FakeApiClient()
    executor._client = client  # type: ignore[assignment]
    executor._sessions["ctx-1"] = Session(session_id="deleted-agent-session", next_index=7)

    asyncio.run(executor.cancel(FakeRequestContext(context_id="ctx-1"), RecordingQueue()))  # type: ignore[arg-type]
    asyncio.run(
        executor._run_and_stream(
            executor._sessions["ctx-1"],
            "next task",
            "task-1",
            "ctx-1",
            RecordingQueue(),  # type: ignore[arg-type]
            metadata=None,
        )
    )

    assert client.cancelled == ["deleted-agent-session"]
    assert calls == [(None, 0)]


@dataclass
class FakeStream:
    to_yield: list[TrajectoryEvent]
    status: TrajectoryStatus = TrajectoryStatus.COMPLETED
    answer: str | None = None
    error: str | None = None
    next_index: int = 0

    async def events(self) -> AsyncIterator[TrajectoryEvent]:
        self.next_index += len(self.to_yield)
        for event in self.to_yield:
            yield event


@dataclass
class FakeTurnClient:
    stream_result: FakeStream
    cancelled: list[str] = field(default_factory=list)

    async def create_session(self, request: SessionRequest) -> str:
        return "agent-api-session"

    async def send_message(self, session_id: str, text: str) -> None:
        pass

    def stream(self, session_id: str, *, from_index: int = 0) -> FakeStream:
        return self.stream_result

    async def cancel(self, session_id: str) -> None:
        self.cancelled.append(session_id)


class CancellingQueue:
    async def enqueue_event(self, event: Any) -> None:
        raise asyncio.CancelledError


def test_a2a_request_cancellation_cancels_active_agent_api_session() -> None:
    event = TrajectoryEvent(type="AgentEvent", data={"kind": "policy_event"}, timestamp=datetime.now(UTC))
    client = FakeTurnClient(FakeStream([event]))
    executor = serve_mod.HoloExecutor(model=None, base_url=None, fake=False, settings=load_holo_settings())
    executor._client = client  # type: ignore[assignment]
    session = Session()

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(
            executor._run_and_stream(
                session,
                "do the thing",
                "task-1",
                "ctx-1",
                CancellingQueue(),  # type: ignore[arg-type]
                metadata=None,
            )
        )

    assert client.cancelled == ["agent-api-session"]
    assert session.session_id is None
