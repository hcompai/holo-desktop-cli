"""Async HTTP client for the hai-agent-runtime agent-API surface."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from types import TracebackType

import httpx
from agent_interface.definition import UserMessageEvent
from agent_interface.specs.session import SessionRequest, SessionStatus
from agp_types import TrajectoryChanges, TrajectoryEvent, TrajectoryStatus

logger = logging.getLogger(__name__)

API_PREFIX = "/api/v2"
# Long-poll window per request; modest to stay under the server's cap and keep Ctrl+C responsive.
POLL_WAIT_S = 10

_KNOWN_STATUSES = frozenset(s.value for s in TrajectoryStatus)


def _coerce_status(payload: object) -> object:
    if isinstance(payload, dict):
        status = payload.get("status")
        if isinstance(status, str) and status not in _KNOWN_STATUSES:
            # End the turn instead of mapping to a non-terminal status: an unknown *terminal* status
            # would otherwise never trip end-of-turn and the stream would poll until external limits hit.
            logger.warning("unrecognized session status %r from runtime; ending turn as failed", status)
            patched = {**payload, "status": TrajectoryStatus.FAILED.value}
            if not patched.get("error"):
                patched["error"] = f"runtime reported unrecognized session status {status!r}"
            return patched
    return payload


class AgentApiClient:
    """Authenticated async client bound to one agent-API base URL."""

    def __init__(self, base_url: str, token: str, *, timeout: float = 60.0) -> None:
        self._http = httpx.AsyncClient(
            base_url=f"{base_url}{API_PREFIX}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=httpx.Timeout(timeout, connect=5.0),
        )

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
        await self._http.aclose()

    async def create_session(self, request: SessionRequest) -> str:
        """Create a session and return its id."""
        resp = await self._http.post("/sessions", json=request.model_dump(mode="json", exclude_none=True))
        resp.raise_for_status()
        return str(resp.json()["id"])

    async def get_changes(
        self, session_id: str, from_index: int, *, wait_for_seconds: int, include_events: bool
    ) -> TrajectoryChanges | None:
        """One long-poll for changes since ``from_index``; ``None`` when nothing arrived (204)."""
        resp = await self._http.get(
            f"/sessions/{session_id}/changes",
            params={"from_index": from_index, "wait_for_seconds": wait_for_seconds, "include_events": include_events},
        )
        if resp.status_code == 204:
            return None
        resp.raise_for_status()
        return TrajectoryChanges.model_validate(_coerce_status(resp.json()))

    async def get_status(self, session_id: str) -> SessionStatus:
        """Live session status; authoritative for terminal detection (``/changes`` 204s past the tail)."""
        resp = await self._http.get(f"/sessions/{session_id}/status")
        resp.raise_for_status()
        return SessionStatus.model_validate(_coerce_status(resp.json()))

    async def send_message(self, session_id: str, text: str) -> None:
        # Body is a server-side tagged union, so the typed model's "type" discriminator is required.
        body = UserMessageEvent(message=text).model_dump(mode="json")
        resp = await self._http.post(f"/sessions/{session_id}/messages", json=body)
        resp.raise_for_status()

    async def pause(self, session_id: str) -> None:
        """Freeze the agent after its current step; pairs with cancel for a responsive stop."""
        resp = await self._http.post(f"/sessions/{session_id}/pause")
        resp.raise_for_status()

    async def cancel(self, session_id: str) -> None:
        resp = await self._http.delete(f"/sessions/{session_id}")
        if resp.status_code not in (200, 204):
            resp.raise_for_status()

    def stream(self, session_id: str, *, from_index: int = 0) -> SessionStream:
        return SessionStream(self, session_id, from_index=from_index)


def _is_end_of_turn(status: TrajectoryStatus) -> bool:
    """Terminal, or IDLE (interactive session answered and awaits the next task)."""
    return status.is_terminal or status == TrajectoryStatus.IDLE


class SessionStream:
    """Tails a session's events to end-of-turn, accumulating the final projection."""

    def __init__(self, client: AgentApiClient, session_id: str, *, from_index: int = 0) -> None:
        self._client = client
        self._session_id = session_id
        self.next_index = from_index
        self.answer: str | dict[str, object] | None = None
        self.status: TrajectoryStatus | None = None
        self.error: str | None = None

    async def events(self) -> AsyncIterator[TrajectoryEvent]:
        """Yield each new ``TrajectoryEvent`` until the session reaches end-of-turn."""
        while True:
            changes = await self._client.get_changes(
                self._session_id, self.next_index, wait_for_seconds=POLL_WAIT_S, include_events=True
            )
            if changes is not None:
                self.next_index += len(changes.new_events)
                if changes.answer is not None:
                    self.answer = changes.answer
                # status + error are one coherent snapshot: track the latest so a recovered
                # session does not finish carrying a stale failure from an earlier batch.
                self.status = changes.status
                self.error = changes.error
                for event in changes.new_events:
                    yield event
                if _is_end_of_turn(changes.status):
                    return
                continue
            status = await self._client.get_status(self._session_id)
            if _is_end_of_turn(status.status):
                await self._finalize(status)
                return

    async def _finalize(self, status: SessionStatus) -> None:
        """Adopt the authoritative status and pick up the final answer the 204 hid from us."""
        self.status = status.status
        self.error = status.error
        if self.answer is not None:
            return
        final = await self._client.get_changes(self._session_id, 0, wait_for_seconds=0, include_events=False)
        if final is not None:
            self.answer = final.answer
            self.error = self.error or final.error
