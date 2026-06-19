"""Shared per-turn session driver for the serve (A2A), acp, and mcp surfaces."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from typing import Protocol

import httpx
from agent_interface.specs.session import SessionRequest
from agp_types import TrajectoryEvent, TrajectoryStatus

from holo_desktop.agent_client.desktop_lock import desktop_turn
from holo_desktop.agent_client.events import answer_text, as_text, is_answer
from holo_desktop.agent_client.requests import build_session_request
from holo_desktop.killswitch.channel import StopSentinel

logger = logging.getLogger(__name__)

SUCCESSFUL_TURN_STATUSES: frozenset[TrajectoryStatus] = frozenset({TrajectoryStatus.COMPLETED, TrajectoryStatus.IDLE})

DEFAULT_INTERACTIVE_IDLE_TIMEOUT_S = 1800
# Runaway guard for surfaces whose caller passes no budget (mcp/acp); generous enough for heavy tasks.
DEFAULT_MAX_STEPS = 150
DEFAULT_MAX_TIME_S = 1800.0
# Cadence at which an in-flight turn checks the kill-switch sentinel.
STOP_POLL_S = 0.25

_DEAD_SESSION_CODES = frozenset({404, 409, 410})


class EventStream(Protocol):
    """Structural view of :class:`~holo_desktop.agent_client.client.SessionStream`."""

    next_index: int
    answer: str | dict[str, object] | None
    status: TrajectoryStatus | None
    error: str | None

    def events(self) -> AsyncIterator[TrajectoryEvent]: ...


class SessionApi(Protocol):
    """The slice of :class:`~holo_desktop.agent_client.client.AgentApiClient` the runner needs."""

    async def create_session(self, request: SessionRequest) -> str: ...

    async def send_message(self, session_id: str, text: str) -> None: ...

    async def pause(self, session_id: str) -> None: ...

    async def cancel(self, session_id: str) -> None: ...

    def stream(self, session_id: str, *, from_index: int = 0) -> EventStream: ...


@dataclass
class Session:
    """Per-context mapping to one agent-API session, with a resume cursor."""

    session_id: str | None = None
    next_index: int = 0
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def reset(self) -> None:
        """Forget the deleted agent-API session while keeping the outer context."""
        self.session_id = None
        self.next_index = 0


@dataclass
class TurnOutcome:
    """Terminal projection of one turn."""

    status: TrajectoryStatus | None
    # Best-effort answer text; "" when the session produced none.
    answer: str
    error: str | None
    # The agent-API session the turn ran against, captured before any stop-driven reset; None when a
    # stop won before the session was created. Authoritative source for reporting the id.
    session_id: str | None


class StopWatcher:
    """Background poll of the stop channel; its task resolves once a stop is filed after the turn began.

    One watcher spans an entire turn — session setup and event streaming — so a kill-switch stop filed
    while the desktop lock is held or the session is being created is observed, not only once streaming
    begins.
    """

    def __init__(self, started_at: float) -> None:
        self._sentinel = StopSentinel(started_at)
        self._task: asyncio.Task[None] | None = None

    def start(self) -> asyncio.Task[None]:
        """Launch the poll loop and return its task to race against the turn's work."""
        task = asyncio.create_task(self._poll())
        self._task = task
        return task

    async def _poll(self) -> None:
        while not self._sentinel.stop_requested():
            await asyncio.sleep(STOP_POLL_S)

    async def aclose(self) -> None:
        """Cancel and reap the poll task; a teardown-time failure is logged, never propagated."""
        task = self._task
        if task is None:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.debug("stop watcher ended with an error during teardown", exc_info=True)
        self._task = None


async def run_turn(
    client: SessionApi,
    session: Session,
    text: str,
    *,
    max_steps: int | None,
    max_time_s: float | None,
    idle_timeout_s: int | None = None,
    on_event: Callable[[TrajectoryEvent], Awaitable[None]],
) -> TurnOutcome:
    """Create or continue the session, stream events through `on_event`, and return the terminal outcome.

    A stop watcher runs for the whole turn, so a kill-switch stop is honored during session setup as
    well as streaming. On a stop the session is paused (immediate freeze) then cancelled, and the
    projection is marked ``INTERRUPTED`` so callers report it without special-casing.
    """
    async with desktop_turn():
        watcher = StopWatcher(time.time())
        watch_task = watcher.start()
        stream: EventStream | None = None
        answer: str | None = None
        session_id: str | None = None
        try:
            stream, stopped = await _open_stream(
                client,
                session,
                text,
                watch_task,
                max_steps=max_steps,
                max_time_s=max_time_s,
                idle_timeout_s=idle_timeout_s,
            )
            # Captured here, before _pause_then_cancel/cancel_session_best_effort forget the session,
            # so the outcome reports the id the turn ran against even after an interrupting stop.
            session_id = session.session_id
            if stream is not None and not stopped:
                answer, stopped = await consume_until_stop(stream, watch_task, on_event=on_event)
            if stopped:
                await _pause_then_cancel(client, session)
                if stream is not None:
                    stream.status = TrajectoryStatus.INTERRUPTED
                    stream.error = None
        except BaseException:
            await cancel_session_best_effort(client, session)
            raise
        finally:
            await watcher.aclose()
            if stream is not None and session.session_id is not None:
                session.next_index = stream.next_index

        return _build_outcome(stream, answer, session_id)


async def _await_or_stop[T](coro: Awaitable[T], watch_task: asyncio.Task[None]) -> tuple[T | None, bool]:
    """Run ``coro`` to completion or until the stop watcher fires; returns ``(result, stopped)``."""
    # First-completed race, not gather/TaskGroup: the watcher's poll loop never returns on its own, so
    # awaiting both would hang. The loser is cancelled and reaped; a watcher failure is re-raised here
    # rather than mistaken for a stop. ``result`` is None exactly when the stop won.
    task: asyncio.Task[T] = asyncio.ensure_future(coro)
    try:
        done, _ = await asyncio.wait({task, watch_task}, return_when=asyncio.FIRST_COMPLETED)
        if task in done:
            return task.result(), False
        watch_task.result()
        return None, True
    finally:
        if not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task


async def _open_stream(
    client: SessionApi,
    session: Session,
    text: str,
    watch_task: asyncio.Task[None],
    *,
    max_steps: int | None,
    max_time_s: float | None,
    idle_timeout_s: int | None,
) -> tuple[EventStream | None, bool]:
    """Open the turn's event stream, racing session setup against the stop watcher.

    Returns ``(stream, stopped)``: the live stream when setup wins, or ``(None, True)`` when a stop is
    filed before the stream opens.
    """

    async def _open() -> EventStream:
        session_id = await _create_or_continue(
            client, session, text, max_steps=max_steps, max_time_s=max_time_s, idle_timeout_s=idle_timeout_s
        )
        return client.stream(session_id, from_index=session.next_index)

    return await _await_or_stop(_open(), watch_task)


async def consume_until_stop(
    stream: EventStream,
    watch_task: asyncio.Task[None],
    *,
    on_event: Callable[[TrajectoryEvent], Awaitable[None]],
) -> tuple[str | None, bool]:
    """Stream a turn to its end or a kill-switch stop, racing the shared stop watcher.

    Returns ``(answer, stopped)``: the best-effort answer text, and whether a stop interrupted the
    turn. Pausing/cancelling the session and marking the projection is the caller's responsibility.

    Args:
        stream: The event stream to consume; its ``status``/``error`` projection is read by callers.
        watch_task: The shared stop-watcher task; its completion means a stop was filed.
        on_event: Async callback invoked for each non-answer event.
    """
    answer: str | None = None

    async def _consume() -> None:
        nonlocal answer
        async for event in stream.events():
            if is_answer(event):
                answer = answer_text(event) or answer
                continue
            try:
                await on_event(event)
            except Exception:
                logger.warning("on_event failed for %s", event.type, exc_info=True)

    # ``_consume`` re-raises any streaming error via ``task.result()`` inside the helper; the answer it
    # accumulates is read back through the nonlocal, so only the stop flag is taken from the return.
    _, stopped = await _await_or_stop(_consume(), watch_task)
    return answer, stopped


def _build_outcome(stream: EventStream | None, answer: str | None, session_id: str | None) -> TurnOutcome:
    """Project the terminal outcome; a stop before the stream opened has no projection to read."""
    if stream is None:
        return TurnOutcome(status=TrajectoryStatus.INTERRUPTED, answer="", error=None, session_id=session_id)
    return TurnOutcome(
        status=stream.status,
        answer=answer if answer is not None else (as_text(stream.answer) or ""),
        error=stream.error,
        session_id=session_id,
    )


async def _create_or_continue(
    client: SessionApi,
    session: Session,
    text: str,
    *,
    max_steps: int | None,
    max_time_s: float | None,
    idle_timeout_s: int | None,
) -> str:
    """Start a new agent-API session, or continue one; recreate if the server expired it."""
    if session.session_id is not None:
        try:
            await client.send_message(session.session_id, text)
            return session.session_id
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code not in _DEAD_SESSION_CODES:
                raise
            session.reset()
    request = build_session_request(
        task=text, max_steps=max_steps, max_time_s=max_time_s, idle_timeout_s=idle_timeout_s
    )
    session.session_id = await client.create_session(request)
    return session.session_id


async def cancel_session_best_effort(client: SessionApi, session: Session) -> None:
    """Best-effort cancel for the agent-API session owned by ``session``."""
    if session.session_id is None:
        return
    session_id = session.session_id
    try:
        await asyncio.shield(client.cancel(session_id))
    except Exception:
        logger.warning("failed to cancel agent-API session %s", session_id, exc_info=True)
    finally:
        session.reset()


async def _pause_then_cancel(client: SessionApi, session: Session) -> None:
    """Pause for an immediate freeze, cancel, then forget the session so the next turn starts fresh.

    Each remote call is best-effort, but the local reset always runs: a cancelled session must never be
    reused by callers (ACP / serve) that keep a long-lived ``Session`` across turns.
    """
    session_id = session.session_id
    if session_id is None:
        return
    try:
        for verb, action in (("pause", client.pause), ("cancel", client.cancel)):
            try:
                await asyncio.shield(action(session_id))
            except Exception:
                logger.warning("failed to %s session %s during stop", verb, session_id, exc_info=True)
    finally:
        session.reset()
