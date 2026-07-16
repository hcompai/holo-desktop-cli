"""SessionApi adapter over the hai-agents SDK, bound to one local runtime.

The agent-API wire protocol (tagged message bodies, 204-vs-status terminal
detection) lives in hai-agents now; this module only maps session_runner's
structural SessionApi/EventStream protocols onto AsyncClient.local(...) and
its AsyncSessionHandles. Two normalizations stay Holo-owned because the
frozen runner/render code depends on them:

- SDK events (typed Fern payloads) flatten back to ``agp_types.TrajectoryEvent``
  with dict ``data`` so events.py / feed / acp / mcp keep parsing them;
- SDK ``ApiError`` translates to ``httpx.HTTPStatusError`` so the runner's
  dead-session recreate path (404/409/410) keeps firing.
"""

from __future__ import annotations

import contextlib
import logging
from collections.abc import AsyncIterator
from types import TracebackType
from typing import TYPE_CHECKING

import httpx
from agent_interface.specs.session import SessionRequest
from agp_types import TrajectoryEvent, TrajectoryStatus
from hai_agents import AsyncClient
from hai_agents.core.api_error import ApiError

if TYPE_CHECKING:
    from hai_agents import AsyncSessionHandle
    from hai_agents.local import LocalRuntime

logger = logging.getLogger(__name__)

_KNOWN_STATUSES = frozenset(s.value for s in TrajectoryStatus)


def _as_httpx_error(exc: ApiError, method: str, url: str) -> httpx.HTTPStatusError:
    """Rehydrate an SDK ApiError as the httpx error shape the frozen session_runner expects."""
    request = httpx.Request(method, url)
    response = httpx.Response(exc.status_code or 500, request=request, text=str(exc.body or ""))
    return httpx.HTTPStatusError(str(exc), request=request, response=response)


@contextlib.asynccontextmanager
async def _api_errors_as_httpx(method: str, url: str) -> AsyncIterator[None]:
    try:
        yield
    except ApiError as exc:
        raise _as_httpx_error(exc, method, url) from exc


def _as_trajectory_event(raw: object) -> TrajectoryEvent:
    """Flatten one SDK SessionEvent (typed pydantic payloads) into the agp wire model."""
    if isinstance(raw, TrajectoryEvent):
        return raw
    if isinstance(raw, dict):
        return TrajectoryEvent.model_validate(raw)
    dump = getattr(raw, "model_dump", None)
    return TrajectoryEvent.model_validate(dump() if callable(dump) else raw)


class AgentApiClient:
    """The session_runner.SessionApi surface, backed by hai-agents local mode."""

    def __init__(self, runtime: LocalRuntime) -> None:
        self._client = AsyncClient.local(runtime=runtime)
        self._base_url = runtime.base_url
        # session_runner drives sessions by id string; handles are per-process,
        # which matches every caller (run/serve/mcp/acp hold one client per process).
        self._handles: dict[str, AsyncSessionHandle] = {}

    async def __aenter__(self) -> AgentApiClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        # The generated AsyncClient exposes no aclose; close its underlying httpx client.
        closer = getattr(self._client, "aclose", None)
        if closer is not None:
            await closer()
            return
        wrapper = getattr(self._client, "_client_wrapper", None)
        http = getattr(getattr(wrapper, "httpx_client", None), "httpx_client", None)
        if http is not None:
            await http.aclose()

    def _handle(self, session_id: str) -> AsyncSessionHandle:
        handle = self._handles.get(session_id)
        if handle is None:
            raise RuntimeError(f"unknown agent-API session {session_id!r}; sessions are per-process")
        return handle

    def _url(self, suffix: str) -> str:
        return f"{self._base_url}/api/v2{suffix}"

    async def create_session(self, request: SessionRequest) -> str:
        """Create a session and return its id."""
        # start_session takes create_session kwargs; the dump is the exact wire
        # body the pre-SDK client POSTed, so requests.py output passes through unmodified.
        async with _api_errors_as_httpx("POST", self._url("/sessions")):
            handle = await self._client.start_session(**request.model_dump(mode="json", exclude_none=True))
        self._handles[handle.id] = handle
        return handle.id

    async def send_message(self, session_id: str, text: str) -> None:
        async with _api_errors_as_httpx("POST", self._url(f"/sessions/{session_id}/messages")):
            await self._handle(session_id).send_message(text)

    async def pause(self, session_id: str) -> None:
        """Freeze the agent after its current step; pairs with cancel for a responsive stop."""
        async with _api_errors_as_httpx("POST", self._url(f"/sessions/{session_id}/pause")):
            await self._handle(session_id).pause()

    async def cancel(self, session_id: str) -> None:
        async with _api_errors_as_httpx("DELETE", self._url(f"/sessions/{session_id}")):
            await self._handle(session_id).cancel()

    def stream(self, session_id: str, *, from_index: int = 0) -> SessionStream:
        return SessionStream(self._handle(session_id), self._url(f"/sessions/{session_id}"), from_index=from_index)


class SessionStream:
    """EventStream projection over AsyncSessionHandle.stream(); field names are the runner's contract."""

    def __init__(self, handle: AsyncSessionHandle, url: str, *, from_index: int = 0) -> None:
        self._handle = handle
        self._url = url
        self.next_index = from_index
        self.answer: str | dict[str, object] | None = None
        self.status: TrajectoryStatus | None = None
        self.error: str | None = None

    async def events(self) -> AsyncIterator[TrajectoryEvent]:
        """Yield each new event until end-of-turn (SDK-owned), then adopt the terminal projection."""
        async with _api_errors_as_httpx("GET", self._url):
            async for event in self._handle.stream(from_index=self.next_index):
                self.next_index += 1
                yield _as_trajectory_event(event)
            status = await self._handle.status()
            self._adopt_status(status.status, status.error)
            # Pick up the final answer the event tail may not carry (the old _finalize behavior).
            final = await self._handle.changes(from_index=0, include_events=False, wait_for_seconds=0)
            if final is not None:
                self.answer = final.answer
                self.error = self.error or final.error

    def _adopt_status(self, raw: object, error: str | None) -> None:
        """Adopt the authoritative status, hardening against statuses this client doesn't know.

        Rehomed from the old client's _coerce_status: an unknown status ends the
        turn as FAILED with an explanatory error instead of crashing the projection
        or reporting a phantom success.
        """
        value = raw.value if isinstance(raw, TrajectoryStatus) else raw
        if isinstance(value, str) and value in _KNOWN_STATUSES:
            self.status = TrajectoryStatus(value)
            self.error = error
            return
        logger.warning("unrecognized session status %r from runtime; ending turn as failed", raw)
        self.status = TrajectoryStatus.FAILED
        self.error = error or f"runtime reported unrecognized session status {raw!r}"
