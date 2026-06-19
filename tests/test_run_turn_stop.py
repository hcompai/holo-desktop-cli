"""run_turn honors a kill-switch stop during session setup as well as streaming."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

import pytest
from agp_types import TrajectoryStatus

from holo_desktop.agent_client import session_runner
from holo_desktop.agent_client.session_runner import Session, run_turn
from holo_desktop.killswitch import channel
from holo_desktop.killswitch.channel import request_stop

SESSION_ID = "agent-api-session"

# A stop filed with a future wall-clock time is honored by any turn that starts before it: a
# deterministic stand-in for "the user pressed Esc mid-turn" without racing the real clock.
FUTURE = 3600.0


@pytest.fixture(autouse=True)
def _fast_isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(channel, "STOP_PATH", tmp_path / "stop")
    monkeypatch.setattr(session_runner, "STOP_POLL_S", 0.01)


def _event() -> object:
    return SimpleNamespace(type="AgentEvent", data={"kind": "policy_event"})


async def _noop(event: object) -> None:
    return None


class _FakeStream:
    def __init__(
        self, events: list[object], *, final_status: TrajectoryStatus, blocks: bool, on_yield: Callable[[], None] | None
    ) -> None:
        self._events = events
        self._final_status = final_status
        self._blocks = blocks
        self._on_yield = on_yield
        self.next_index = 0
        self.answer: str | None = None
        self.status: TrajectoryStatus | None = None
        self.error: str | None = None

    async def events(self):
        for event in self._events:
            self.next_index += 1
            yield event
            if self._on_yield is not None:
                self._on_yield()
        if self._blocks:
            await asyncio.sleep(3600)
        self.status = self._final_status


@dataclass
class _FakeClient:
    stream_result: _FakeStream
    block_create: bool = False
    created: int = 0
    paused: list[str] = field(default_factory=list)
    cancelled: list[str] = field(default_factory=list)
    messaged: list[str] = field(default_factory=list)

    async def create_session(self, request: object) -> str:
        if self.block_create:
            await asyncio.Event().wait()  # never returns: setup is stuck until the turn is cancelled
        self.created += 1
        return SESSION_ID

    async def send_message(self, session_id: str, text: str) -> None:
        self.messaged.append(session_id)

    def stream(self, session_id: str, *, from_index: int = 0) -> _FakeStream:
        return self.stream_result

    async def pause(self, session_id: str) -> None:
        self.paused.append(session_id)

    async def cancel(self, session_id: str) -> None:
        self.cancelled.append(session_id)


def test_stop_during_setup_interrupts_before_streaming() -> None:
    """Bug #1: a stop filed while the session is still being created must not be ignored until streaming."""

    async def go() -> None:
        request_stop(now=time.time() + FUTURE)
        client = _FakeClient(
            _FakeStream([], final_status=TrajectoryStatus.COMPLETED, blocks=False, on_yield=None), block_create=True
        )
        session = Session()

        outcome = await run_turn(client, session, "task", max_steps=None, max_time_s=None, on_event=_noop)

        assert outcome.status is TrajectoryStatus.INTERRUPTED
        assert client.created == 0, "the stream must never open when a stop wins during setup"

    asyncio.run(asyncio.wait_for(go(), timeout=5.0))


def test_stop_during_streaming_pauses_then_cancels_and_marks_interrupted() -> None:
    async def go() -> None:
        stream = _FakeStream(
            [_event()],
            final_status=TrajectoryStatus.COMPLETED,
            blocks=True,
            on_yield=lambda: request_stop(now=time.time() + FUTURE),
        )
        client = _FakeClient(stream)
        session = Session()

        outcome = await run_turn(client, session, "task", max_steps=None, max_time_s=None, on_event=_noop)

        assert client.paused == [SESSION_ID]
        assert client.cancelled == [SESSION_ID]
        assert outcome.status is TrajectoryStatus.INTERRUPTED

    asyncio.run(asyncio.wait_for(go(), timeout=5.0))


def test_stop_during_streaming_reports_the_session_it_ran_against() -> None:
    """The stop resets the session, but the outcome must still report the id the turn ran against,
    so an interrupted run never persists a blank session_id (the kill-switch contract)."""

    async def go() -> None:
        stream = _FakeStream(
            [_event()],
            final_status=TrajectoryStatus.COMPLETED,
            blocks=True,
            on_yield=lambda: request_stop(now=time.time() + FUTURE),
        )
        client = _FakeClient(stream)
        session = Session()

        outcome = await run_turn(client, session, "task", max_steps=None, max_time_s=None, on_event=_noop)

        assert session.session_id is None, "the stopped session is forgotten locally"
        assert outcome.session_id == SESSION_ID, "yet the outcome remembers the id it ran against"

    asyncio.run(asyncio.wait_for(go(), timeout=5.0))


def test_stop_during_setup_has_no_session_to_report() -> None:
    """A stop that wins before the session is created leaves no id to report — None, not a guess."""

    async def go() -> None:
        request_stop(now=time.time() + FUTURE)
        client = _FakeClient(
            _FakeStream([], final_status=TrajectoryStatus.COMPLETED, blocks=False, on_yield=None), block_create=True
        )
        outcome = await run_turn(client, Session(), "task", max_steps=None, max_time_s=None, on_event=_noop)

        assert outcome.status is TrajectoryStatus.INTERRUPTED
        assert outcome.session_id is None

    asyncio.run(asyncio.wait_for(go(), timeout=5.0))


def test_stop_forgets_session_so_next_turn_starts_fresh() -> None:
    """A kill-switch stop must reset the session, so the next turn creates a new one instead of
    messaging into the just-cancelled session (the reuse bug on ACP / holo serve)."""

    async def go() -> None:
        stream = _FakeStream(
            [_event()],
            final_status=TrajectoryStatus.COMPLETED,
            blocks=True,
            on_yield=lambda: request_stop(now=time.time() + FUTURE),
        )
        client = _FakeClient(stream)
        session = Session()

        await run_turn(client, session, "task", max_steps=None, max_time_s=None, on_event=_noop)
        assert session.session_id is None, "a stopped session must be forgotten, not reused"
        assert session.next_index == 0

        # Second turn with the stop now stale: it must start a brand-new session, never reuse the dead id.
        request_stop(now=time.time() - FUTURE)
        client.stream_result = _FakeStream(
            [_event()], final_status=TrajectoryStatus.COMPLETED, blocks=False, on_yield=None
        )
        outcome = await run_turn(client, session, "again", max_steps=None, max_time_s=None, on_event=_noop)

        assert client.created == 2, "the cancelled session must not be reused; a fresh one is created"
        assert client.messaged == [], "no send_message may target the cancelled session"
        assert outcome.status is TrajectoryStatus.COMPLETED

    asyncio.run(asyncio.wait_for(go(), timeout=5.0))


def test_clean_turn_is_not_interrupted() -> None:
    async def go() -> None:
        client = _FakeClient(
            _FakeStream([_event()], final_status=TrajectoryStatus.COMPLETED, blocks=False, on_yield=None)
        )
        session = Session()

        outcome = await run_turn(client, session, "task", max_steps=None, max_time_s=None, on_event=_noop)

        assert client.paused == []
        assert client.cancelled == []
        assert outcome.status is TrajectoryStatus.COMPLETED

    asyncio.run(asyncio.wait_for(go(), timeout=5.0))


def test_stale_stop_before_turn_is_ignored() -> None:
    async def go() -> None:
        request_stop(now=time.time() - FUTURE)  # filed long before this turn began
        client = _FakeClient(
            _FakeStream([_event()], final_status=TrajectoryStatus.COMPLETED, blocks=False, on_yield=None)
        )
        session = Session()

        outcome = await run_turn(client, session, "task", max_steps=None, max_time_s=None, on_event=_noop)

        assert client.paused == []
        assert outcome.status is TrajectoryStatus.COMPLETED

    asyncio.run(asyncio.wait_for(go(), timeout=5.0))
