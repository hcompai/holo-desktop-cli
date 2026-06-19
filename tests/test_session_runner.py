"""Behavioural tests for the shared session-turn driver (`agent_client.session_runner`).

Drives `run_turn` with in-memory fakes mirroring the agent-API wire shapes:
create-vs-continue, answer folding, event forwarding, and resume-cursor
semantics (including the failure path).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime

import httpx
import pytest
from agent_interface.specs.session import SessionRequest
from agp_types import TrajectoryEvent, TrajectoryStatus

from holo_desktop.agent_client.session_runner import Session, run_turn

SESSION_ID = "agent-api-session"


def _event(kind: str, **data: object) -> TrajectoryEvent:
    return TrajectoryEvent(type="AgentEvent", data={"kind": kind, **data}, timestamp=datetime.now(UTC))


def _http_status_error(code: int) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "http://runtime.local")
    return httpx.HTTPStatusError("dead", request=request, response=httpx.Response(code, request=request))


@dataclass
class FakeStream:
    to_yield: list[TrajectoryEvent]
    status: TrajectoryStatus
    answer: str | None = None
    error: str | None = None
    next_index: int = 0
    raise_after: Exception | None = None

    async def events(self) -> AsyncIterator[TrajectoryEvent]:
        # Mirrors SessionStream: the cursor advances past a batch before yielding it.
        self.next_index += len(self.to_yield)
        for event in self.to_yield:
            yield event
        if self.raise_after is not None:
            raise self.raise_after


@dataclass
class FakeApiClient:
    stream_result: FakeStream
    created: list[SessionRequest] = field(default_factory=list)
    sent: list[tuple[str, str]] = field(default_factory=list)
    cancelled: list[str] = field(default_factory=list)
    stream_from_index: int | None = None
    cancel_on_send: bool = False
    send_status_error: int | None = None

    async def create_session(self, request: SessionRequest) -> str:
        self.created.append(request)
        return SESSION_ID

    async def send_message(self, session_id: str, text: str) -> None:
        if self.cancel_on_send:
            raise asyncio.CancelledError
        if self.send_status_error is not None:
            raise _http_status_error(self.send_status_error)
        self.sent.append((session_id, text))

    def stream(self, session_id: str, *, from_index: int = 0) -> FakeStream:
        self.stream_from_index = from_index
        return self.stream_result

    async def cancel(self, session_id: str) -> None:
        self.cancelled.append(session_id)


async def _collect(event: TrajectoryEvent) -> None:
    pass


def test_first_turn_creates_session_with_budgets() -> None:
    client = FakeApiClient(FakeStream([], status=TrajectoryStatus.COMPLETED, answer="done"))
    session = Session()

    outcome = asyncio.run(
        run_turn(client, session, "do the thing", max_steps=7, max_time_s=60.0, idle_timeout_s=120, on_event=_collect)
    )

    assert session.session_id == SESSION_ID
    assert len(client.created) == 1
    assert client.created[0].max_steps == 7
    assert client.created[0].max_time_s == 60.0
    assert client.created[0].idle_timeout_s == 120
    assert client.sent == []
    assert outcome.status == TrajectoryStatus.COMPLETED
    assert outcome.answer == "done"


def test_second_turn_continues_with_send_message_from_cursor() -> None:
    client = FakeApiClient(FakeStream([], status=TrajectoryStatus.COMPLETED, answer="again"))
    session = Session(session_id=SESSION_ID, next_index=5)

    asyncio.run(run_turn(client, session, "follow up", max_steps=None, max_time_s=None, on_event=_collect))

    assert client.created == []
    assert client.sent == [(SESSION_ID, "follow up")]
    assert client.stream_from_index == 5


def test_reset_forgets_session_and_resume_cursor() -> None:
    session = Session(session_id=SESSION_ID, next_index=5)

    session.reset()

    assert session.session_id is None
    assert session.next_index == 0


def test_answer_events_fold_into_outcome_and_are_not_forwarded() -> None:
    events = [_event("policy_event"), _event("answer_event", answer="from-event"), _event("tool_result_event")]
    client = FakeApiClient(FakeStream(events, status=TrajectoryStatus.COMPLETED, answer="from-stream"))
    session = Session()
    forwarded: list[TrajectoryEvent] = []

    async def record(event: TrajectoryEvent) -> None:
        forwarded.append(event)

    outcome = asyncio.run(run_turn(client, session, "task", max_steps=None, max_time_s=None, on_event=record))

    assert [e.data["kind"] for e in forwarded if isinstance(e.data, dict)] == ["policy_event", "tool_result_event"]
    assert outcome.answer == "from-event", "the answer event wins over the stream projection"


def test_answer_falls_back_to_stream_projection_then_empty() -> None:
    client = FakeApiClient(FakeStream([], status=TrajectoryStatus.COMPLETED, answer="projected"))
    outcome = asyncio.run(run_turn(client, Session(), "t", max_steps=None, max_time_s=None, on_event=_collect))
    assert outcome.answer == "projected"

    client = FakeApiClient(FakeStream([], status=TrajectoryStatus.FAILED, error="boom"))
    outcome = asyncio.run(run_turn(client, Session(), "t", max_steps=None, max_time_s=None, on_event=_collect))
    assert outcome.answer == ""
    assert outcome.error == "boom"
    assert outcome.status == TrajectoryStatus.FAILED


def test_on_event_failure_is_isolated_and_does_not_sink_the_turn() -> None:
    events = [_event("policy_event"), _event("policy_event")]
    client = FakeApiClient(FakeStream(events, status=TrajectoryStatus.COMPLETED, answer="done"))
    session = Session()

    async def explode(event: TrajectoryEvent) -> None:
        raise RuntimeError("renderer broke")

    outcome = asyncio.run(run_turn(client, session, "task", max_steps=None, max_time_s=None, on_event=explode))

    assert outcome.answer == "done"
    assert session.next_index == 2, "a failed render must not cause the next turn to replay events"
    assert client.cancelled == [], "a renderer error must not cancel the live agent-API session"


def test_cancelled_turn_cancels_and_resets_agent_api_session() -> None:
    client = FakeApiClient(FakeStream([_event("policy_event")], status=TrajectoryStatus.COMPLETED))
    session = Session()

    async def cancel_on_event(event: TrajectoryEvent) -> None:
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(run_turn(client, session, "task", max_steps=None, max_time_s=None, on_event=cancel_on_event))

    assert client.cancelled == [SESSION_ID]
    assert session.session_id is None
    assert session.next_index == 0


def test_cancelled_continuation_cancels_and_resets_existing_agent_api_session() -> None:
    client = FakeApiClient(FakeStream([], status=TrajectoryStatus.COMPLETED), cancel_on_send=True)
    session = Session(session_id=SESSION_ID, next_index=9)

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(run_turn(client, session, "follow up", max_steps=None, max_time_s=None, on_event=_collect))

    assert client.cancelled == [SESSION_ID]
    assert session.session_id is None
    assert session.next_index == 0


def test_expired_session_is_recreated_on_continuation() -> None:
    client = FakeApiClient(FakeStream([], status=TrajectoryStatus.IDLE, answer="ok"), send_status_error=404)
    session = Session(session_id="stale", next_index=9)

    outcome = asyncio.run(run_turn(client, session, "follow up", max_steps=None, max_time_s=None, on_event=_collect))

    assert len(client.created) == 1, "a server-expired session must be recreated, not messaged into the void"
    assert session.session_id == SESSION_ID
    assert outcome.answer == "ok"


def test_agent_api_failure_cancels_the_orphaned_session() -> None:
    client = FakeApiClient(
        FakeStream([_event("policy_event")], status=TrajectoryStatus.RUNNING, raise_after=httpx.ConnectError("down"))
    )
    session = Session()

    with pytest.raises(httpx.ConnectError):
        asyncio.run(run_turn(client, session, "task", max_steps=None, max_time_s=None, on_event=_collect))

    assert client.cancelled == [SESSION_ID], "an agent-API failure mid-turn must cancel the still-running session"
    assert session.session_id is None
