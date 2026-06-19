"""Behavioural contract tests for ``agent_client.client`` against a fake agent-API server.

The fake serves the same wire shapes as the canonical ``hai-agent-api`` router
(scripted ``/changes`` + ``/status`` responses) and records every request, so
the tests can assert both client behaviour and that outgoing bodies validate
against the real ``agent_interface`` models.

Covers the two contract pitfalls documented in the SDK's polling helpers:
- ``POST /messages`` takes a discriminated ``UserMessageEvent | UserMessageBatch``
  (a bare ``{"message": ...}`` is rejected by the server's tagged union);
- ``GET /changes`` 204s whenever no new events exist past ``from_index`` —
  even after the session finished — so ``/status`` is authoritative for
  terminal detection.
"""

from __future__ import annotations

import asyncio
import datetime
import json
import threading
from collections import deque
from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Annotated, Literal
from urllib.parse import parse_qs, urlparse

from agent_interface.definition import UserMessageEvent
from agent_interface.specs.session import SessionRequest, SessionStatus
from agp_types import TrajectoryEvent, TrajectoryStatus
from pydantic import BaseModel, Field, TypeAdapter

from holo_desktop.agent_client.client import AgentApiClient, SessionStream

SESSION_ID = "11111111-2222-3333-4444-555555555555"
TOKEN = "test-token"
STREAM_TIMEOUT_S = 5.0


class _UserMessageBatch(BaseModel):
    """Test replica of ``agent_api.models.session.UserMessageBatch`` (not vendored in hai-agent-api)."""

    type: Literal["batch"] = "batch"
    messages: list[UserMessageEvent] = Field(min_length=1)


# Mirror of the server-side ``SendMessage`` body: a *tagged* union, so payloads
# without an explicit ``type`` are rejected exactly like the real router does.
_SEND_MESSAGE_ADAPTER: TypeAdapter[UserMessageEvent | _UserMessageBatch] = TypeAdapter(
    Annotated[UserMessageEvent | _UserMessageBatch, Field(discriminator="type")]
)


@dataclass
class RecordedRequest:
    method: str
    path: str
    query: dict[str, list[str]]
    body: dict | None
    authorization: str | None


@dataclass
class FakeAgentApi:
    """Scripted responses + a log of everything the client sent."""

    # Each GET /changes pops the next entry; None -> 204. Exhausted -> 204.
    changes: deque[dict | None] = field(default_factory=deque)
    # Each GET /status pops the next entry; the last one sticks when exhausted.
    statuses: deque[dict] = field(default_factory=deque)
    requests: list[RecordedRequest] = field(default_factory=list)
    _last_status: dict | None = None

    def next_changes(self) -> dict | None:
        return self.changes.popleft() if self.changes else None

    def next_status(self) -> dict:
        if self.statuses:
            self._last_status = self.statuses.popleft()
        assert self._last_status is not None, "fake server got /status request but no status was scripted"
        return self._last_status


def _make_handler(api: FakeAgentApi) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:  # stdlib signature; silences request logs
            return

        def _record(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
            api.requests.append(
                RecordedRequest(
                    method=self.command,
                    path=urlparse(self.path).path,
                    query=parse_qs(urlparse(self.path).query),
                    body=json.loads(raw) if raw else None,
                    authorization=self.headers.get("Authorization"),
                )
            )

        def _json(self, status: int, payload: dict | None) -> None:
            self.send_response(status)
            if payload is None:
                self.end_headers()
                return
            data = json.dumps(payload).encode("utf-8")
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self) -> None:
            self._record()
            path = urlparse(self.path).path
            if path == "/api/v2/sessions":
                self._json(200, {"id": SESSION_ID})
            elif path.endswith("/messages") or path.endswith("/pause"):
                self._json(202, None)
            else:
                self._json(404, None)

        def do_GET(self) -> None:
            self._record()
            path = urlparse(self.path).path
            if path.endswith("/changes"):
                payload = api.next_changes()
                self._json(204 if payload is None else 200, payload)
            elif path.endswith("/status"):
                self._json(200, api.next_status())
            else:
                self._json(404, None)

        def do_DELETE(self) -> None:
            self._record()
            self._json(204, None)

    return Handler


@contextmanager
def _serve(api: FakeAgentApi) -> Iterator[str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _make_handler(api))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        thread.join(timeout=5.0)


def _event(kind: str, **data: object) -> dict:
    return {
        "type": "AgentEvent",
        "data": {"kind": kind, **data},
        "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
    }


def _changes(status: str, *, events: list[dict], answer: str | None, error: str | None) -> dict:
    return {"status": status, "new_events": events, "answer": answer, "error": error}


def _status(status: str, *, error: str | None) -> dict:
    return {"status": status, "error": error, "steps": 0}


async def _collect(events: AsyncIterator[TrajectoryEvent]) -> list[TrajectoryEvent]:
    return [event async for event in events]


def _run_stream(api: FakeAgentApi, *, from_index: int) -> tuple[list[TrajectoryEvent], SessionStream]:
    """Stream a session to end-of-turn against the fake; bounded so a 204 spin fails the test instead of hanging."""

    async def go(url: str) -> tuple[list[TrajectoryEvent], SessionStream]:
        async with AgentApiClient(url, TOKEN) as client:
            stream = client.stream(SESSION_ID, from_index=from_index)
            collected = await asyncio.wait_for(_collect(stream.events()), timeout=STREAM_TIMEOUT_S)
            return collected, stream

    with _serve(api) as url:
        return asyncio.run(go(url))


# --- request bodies -------------------------------------------------------


def test_create_session_sends_bearer_token_and_returns_id() -> None:
    api = FakeAgentApi()
    with _serve(api) as url:

        async def go() -> str:
            async with AgentApiClient(url, TOKEN) as client:
                return await client.create_session(SessionRequest(agent="holo", messages="say hi"))

        session_id = asyncio.run(go())

    assert session_id == SESSION_ID
    (req,) = api.requests
    assert req.path == "/api/v2/sessions"
    assert req.authorization == f"Bearer {TOKEN}"


def test_send_message_body_is_a_tagged_user_message_event() -> None:
    api = FakeAgentApi()
    with _serve(api) as url:

        async def go() -> None:
            async with AgentApiClient(url, TOKEN) as client:
                await client.send_message(SESSION_ID, "follow-up")

        asyncio.run(go())

    (req,) = api.requests
    assert req.path == f"/api/v2/sessions/{SESSION_ID}/messages"
    assert req.body is not None
    # Must survive the server's discriminated union: requires an explicit type tag.
    parsed = _SEND_MESSAGE_ADAPTER.validate_python(req.body)
    assert isinstance(parsed, UserMessageEvent)
    assert parsed.message == "follow-up"


def test_pause_posts_to_the_pause_endpoint() -> None:
    api = FakeAgentApi()
    with _serve(api) as url:

        async def go() -> None:
            async with AgentApiClient(url, TOKEN) as client:
                await client.pause(SESSION_ID)

        asyncio.run(go())

    (req,) = api.requests
    assert req.method == "POST"
    assert req.path == f"/api/v2/sessions/{SESSION_ID}/pause"
    assert req.authorization == f"Bearer {TOKEN}"


# --- streaming ------------------------------------------------------------


def test_stream_yields_events_until_terminal_changes() -> None:
    api = FakeAgentApi(
        changes=deque(
            [
                _changes("running", events=[_event("policy_event"), _event("tool_result")], answer=None, error=None),
                _changes("completed", events=[_event("answer_event", answer="done")], answer="done", error=None),
            ]
        )
    )
    events, stream = _run_stream(api, from_index=0)
    assert len(events) == 3
    assert stream.status == TrajectoryStatus.COMPLETED
    assert stream.answer == "done"
    assert stream.next_index == 3


def test_stream_ends_via_status_when_changes_204s_after_completion() -> None:
    # The spin case: the session already finished, so /changes 204s forever
    # past our cursor. /status must be consulted, and the final answer fetched.
    api = FakeAgentApi(
        changes=deque([None, _changes("completed", events=[], answer="late answer", error=None)]),
        statuses=deque([_status("completed", error=None)]),
    )
    events, stream = _run_stream(api, from_index=0)
    assert events == []
    assert stream.status == TrajectoryStatus.COMPLETED
    assert stream.answer == "late answer"


def test_stream_resume_with_cursor_at_tail_does_not_spin() -> None:
    api = FakeAgentApi(
        changes=deque([None, _changes("completed", events=[], answer="prior answer", error=None)]),
        statuses=deque([_status("completed", error=None)]),
    )
    events, stream = _run_stream(api, from_index=3)
    assert events == []
    assert stream.next_index == 3
    assert stream.status == TrajectoryStatus.COMPLETED


def test_stream_204_while_running_keeps_polling() -> None:
    api = FakeAgentApi(
        changes=deque(
            [
                None,
                _changes("completed", events=[_event("answer_event", answer="ok")], answer="ok", error=None),
            ]
        ),
        statuses=deque([_status("running", error=None)]),
    )
    events, stream = _run_stream(api, from_index=0)
    assert len(events) == 1
    assert stream.status == TrajectoryStatus.COMPLETED


def test_stream_idle_status_ends_the_turn() -> None:
    # Interactive sessions (idle_timeout_s) go IDLE after answering; that is
    # end-of-turn for a streaming consumer, not a reason to poll forever.
    api = FakeAgentApi(
        changes=deque([None, _changes("idle", events=[], answer="turn answer", error=None)]),
        statuses=deque([_status("idle", error=None)]),
    )
    events, stream = _run_stream(api, from_index=0)
    assert events == []
    assert stream.status == TrajectoryStatus.IDLE
    assert stream.answer == "turn answer"


def test_stream_idle_changes_fast_path_ends_the_turn() -> None:
    api = FakeAgentApi(
        changes=deque([_changes("idle", events=[_event("answer_event", answer="hi")], answer="hi", error=None)]),
    )
    events, stream = _run_stream(api, from_index=0)
    assert len(events) == 1
    assert stream.status == TrajectoryStatus.IDLE
    assert stream.answer == "hi"


def test_stream_failed_session_reports_error() -> None:
    api = FakeAgentApi(
        changes=deque([None]),
        statuses=deque([_status("failed", error="boom")]),
    )
    events, stream = _run_stream(api, from_index=0)
    assert events == []
    assert stream.status == TrajectoryStatus.FAILED
    assert stream.error == "boom"


def test_stream_does_not_carry_stale_error_after_recovery() -> None:
    # An error in an early batch must not survive a later successful batch that clears it.
    api = FakeAgentApi(
        changes=deque(
            [
                _changes("running", events=[_event("policy_event")], answer=None, error="transient glitch"),
                _changes("completed", events=[_event("answer_event", answer="ok")], answer="ok", error=None),
            ]
        )
    )
    _events, stream = _run_stream(api, from_index=0)
    assert stream.status == TrajectoryStatus.COMPLETED
    assert stream.error is None


def test_stream_unknown_status_ends_turn_as_failed() -> None:
    # An unrecognized status must end the turn, not be treated as non-terminal "running":
    # an unknown *terminal* status would otherwise poll until external limits hit.
    api = FakeAgentApi(changes=deque([_changes("quantum_flux", events=[], answer=None, error=None)]))
    events, stream = _run_stream(api, from_index=0)
    assert events == []
    assert stream.status == TrajectoryStatus.FAILED
    assert stream.error is not None and "quantum_flux" in stream.error


def test_get_status_hits_the_status_endpoint() -> None:
    api = FakeAgentApi(statuses=deque([_status("running", error=None)]))
    with _serve(api) as url:

        async def go() -> SessionStatus:
            async with AgentApiClient(url, TOKEN) as client:
                return await client.get_status(SESSION_ID)

        status = asyncio.run(go())

    assert status.status == TrajectoryStatus.RUNNING
    (req,) = api.requests
    assert req.path == f"/api/v2/sessions/{SESSION_ID}/status"
