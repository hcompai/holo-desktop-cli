"""Behavioural tests for `HoloAcpAgent.prompt` terminal-status → ACP stop_reason mapping.

Drives `prompt()` with a fake agent-API client (scripted `SessionStream` outcome)
and a recording ACP connection, asserting each terminal `TrajectoryStatus` maps
to the right `stop_reason` and final agent message.
"""

from __future__ import annotations

import asyncio
import importlib
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import pytest
from acp.schema import AgentMessageChunk, TextContentBlock
from agp_types import TrajectoryEvent, TrajectoryStatus

from holo_desktop.agent_client.session_runner import Session
from holo_desktop.cli.acp import HoloAcpAgent

acp_mod = importlib.import_module("holo_desktop.cli.acp")

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
    created: list[str] = field(default_factory=list)
    sent: list[tuple[str, str]] = field(default_factory=list)
    cancelled: list[str] = field(default_factory=list)

    async def create_session(self, request: object) -> str:
        session_id = f"{SESSION_ID}-{len(self.created) + 1}"
        self.created.append(session_id)
        return session_id

    async def send_message(self, session_id: str, text: str) -> None:
        self.sent.append((session_id, text))

    def stream(self, session_id: str, *, from_index: int = 0) -> FakeStream:
        return self.outcome

    async def cancel(self, session_id: str) -> None:
        self.cancelled.append(session_id)

    async def aclose(self) -> None:
        pass


@dataclass
class RecordingConn:
    updates: list[Any] = field(default_factory=list)

    async def session_update(self, session_id: str, update: Any) -> None:  # Any: ACP union of update payloads
        self.updates.append(update)


def _prompt_with(outcome: FakeStream) -> tuple[str, RecordingConn]:
    agent = HoloAcpAgent()
    conn = RecordingConn()
    agent.on_connect(conn)  # type: ignore[arg-type]  # structural stand-in for acp.Client
    agent._client = FakeApiClient(outcome)  # type: ignore[assignment]

    async def go() -> str:
        new = await agent.new_session(cwd="/tmp")
        response = await agent.prompt(
            prompt=[TextContentBlock(type="text", text="do the thing")],
            session_id=new.session_id,
        )
        return response.stop_reason

    return asyncio.run(go()), conn


def _agent_message_texts(conn: RecordingConn) -> list[str]:
    return [u.content.text for u in conn.updates if isinstance(u, AgentMessageChunk)]


def test_completed_maps_to_end_turn_with_answer() -> None:
    stop_reason, conn = _prompt_with(FakeStream(status=TrajectoryStatus.COMPLETED, answer="all done"))
    assert stop_reason == "end_turn"
    assert _agent_message_texts(conn) == ["all done"]


def test_failed_maps_to_refusal_with_error_message() -> None:
    stop_reason, conn = _prompt_with(FakeStream(status=TrajectoryStatus.FAILED, error="boom"))
    assert stop_reason == "refusal"
    assert _agent_message_texts(conn) == ["boom"]


def test_interrupted_maps_to_cancelled() -> None:
    stop_reason, conn = _prompt_with(FakeStream(status=TrajectoryStatus.INTERRUPTED))
    assert stop_reason == "cancelled"
    assert _agent_message_texts(conn) == []


def test_timed_out_is_not_reported_as_a_successful_turn() -> None:
    stop_reason, conn = _prompt_with(FakeStream(status=TrajectoryStatus.TIMED_OUT))
    assert stop_reason == "max_turn_requests"
    messages = _agent_message_texts(conn)
    assert len(messages) == 1
    assert "timed out" in messages[0]


def test_timed_out_surfaces_the_session_error_when_present() -> None:
    stop_reason, conn = _prompt_with(FakeStream(status=TrajectoryStatus.TIMED_OUT, error="budget exhausted"))
    assert stop_reason == "max_turn_requests"
    assert _agent_message_texts(conn) == ["budget exhausted"]


def test_cancel_resets_agent_api_session_before_next_prompt() -> None:
    agent = HoloAcpAgent()
    conn = RecordingConn()
    client = FakeApiClient(FakeStream(status=TrajectoryStatus.COMPLETED, answer="done"))
    agent.on_connect(conn)  # type: ignore[arg-type]  # structural stand-in for acp.Client
    agent._client = client  # type: ignore[assignment]

    async def go() -> None:
        new = await agent.new_session(cwd="/tmp")
        await agent.prompt(prompt=[TextContentBlock(type="text", text="first")], session_id=new.session_id)
        session = agent._sessions[new.session_id]
        session.next_index = 9

        await agent.cancel(new.session_id)
        await agent.prompt(prompt=[TextContentBlock(type="text", text="second")], session_id=new.session_id)

    asyncio.run(go())

    assert client.cancelled == [f"{SESSION_ID}-1"]
    assert client.created == [f"{SESSION_ID}-1", f"{SESSION_ID}-2"]
    assert client.sent == []


def test_prompt_coroutine_cancellation_cancels_active_agent_api_session(monkeypatch: pytest.MonkeyPatch) -> None:
    agent = HoloAcpAgent()
    conn = RecordingConn()
    event = TrajectoryEvent(type="AgentEvent", data={"kind": "policy_event"}, timestamp=datetime.now(UTC))
    client = FakeApiClient(FakeStream(status=TrajectoryStatus.COMPLETED, answer="done", to_yield=[event]))
    agent.on_connect(conn)  # type: ignore[arg-type]  # structural stand-in for acp.Client
    agent._client = client  # type: ignore[assignment]

    async def cancelled_translate(session_id: str, event: TrajectoryEvent) -> None:
        raise asyncio.CancelledError

    monkeypatch.setattr(agent, "_translate", cancelled_translate)

    async def go() -> Session:
        new = await agent.new_session(cwd="/tmp")
        session = agent._sessions[new.session_id]
        with pytest.raises(asyncio.CancelledError):
            await agent.prompt(prompt=[TextContentBlock(type="text", text="first")], session_id=new.session_id)
        return session

    session = asyncio.run(go())

    assert client.cancelled == [f"{SESSION_ID}-1"]
    assert session.session_id is None


def test_new_session_refuses_when_every_slot_is_busy() -> None:
    # All slots hold an in-flight prompt: refuse rather than grow _sessions past the cap.
    agent = HoloAcpAgent()
    agent._client = FakeApiClient(FakeStream(status=TrajectoryStatus.COMPLETED))  # type: ignore[assignment]

    async def go() -> None:
        held = []
        for i in range(acp_mod.MAX_ACTIVE_SESSIONS):
            session = Session()
            await session.lock.acquire()
            held.append(session)
            agent._sessions[f"busy-{i}"] = session
        with pytest.raises(acp_mod.RequestError):
            await agent.new_session(cwd="/tmp")
        assert len(agent._sessions) == acp_mod.MAX_ACTIVE_SESSIONS
        for session in held:
            session.lock.release()

    asyncio.run(go())


def test_aclose_cancels_active_agent_api_sessions_before_closing() -> None:
    agent = HoloAcpAgent()
    client = FakeApiClient(FakeStream(status=TrajectoryStatus.COMPLETED, answer="done"))
    agent._client = client  # type: ignore[assignment]
    agent._sessions["one"] = Session(session_id="agent-one", next_index=3)
    agent._sessions["two"] = Session()
    agent._sessions["three"] = Session(session_id="agent-three", next_index=7)

    asyncio.run(agent.aclose())

    assert client.cancelled == ["agent-one", "agent-three"]
    assert agent._sessions["one"].session_id is None
    assert agent._sessions["three"].session_id is None
