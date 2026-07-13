"""SessionApi adapter mapping over fake hai-agents handles.

The wire protocol moved into the SDK (plan 002); these tests only pin the
mapping Holo owns: SessionRequest passthrough, per-session handle routing for
send/pause/cancel, the EventStream projection session_runner reads, the
agp_types normalization of SDK events/statuses, and the ApiError -> httpx
translation the frozen session_runner's dead-session recovery depends on.
"""

from __future__ import annotations

import asyncio
import datetime
from types import SimpleNamespace

import httpx
import pytest
from agp_types import TrajectoryEvent, TrajectoryStatus
from hai_agents.core.api_error import ApiError
from pydantic import BaseModel

from holo_desktop.agent_client import client as client_module
from holo_desktop.agent_client import events as events_module
from holo_desktop.agent_client.client import AgentApiClient
from holo_desktop.agent_client.requests import build_session_request


class _TypedAnswerData(BaseModel):
    """Stands in for a Fern typed event payload (a model, not a dict)."""

    kind: str = "answer_event"
    answer: str = "done"


class _FernishEvent(BaseModel):
    """Shape of an SDK SessionEvent: typed data that Holo must flatten back to dicts."""

    type: str = "AgentEvent"
    timestamp: datetime.datetime = datetime.datetime(2026, 6, 30, tzinfo=datetime.UTC)
    data: _TypedAnswerData = _TypedAnswerData()


class _FakeHandle:
    def __init__(self, events: list[object], *, status: str = "completed") -> None:
        self.id = "s-1"
        self.sent: list[object] = []
        self.paused = 0
        self.cancelled = 0
        self.send_error: Exception | None = None
        self._events = events
        self._status = status

    async def send_message(self, message: object) -> None:
        if self.send_error is not None:
            raise self.send_error
        self.sent.append(message)

    async def pause(self) -> None:
        self.paused += 1

    async def cancel(self) -> None:
        self.cancelled += 1

    async def status(self):
        # The SDK reports plain wire strings (Fern Literal), not agp enums.
        return SimpleNamespace(status=self._status, error=None)

    async def changes(self, *, from_index: int = 0, **_kwargs: object):
        return SimpleNamespace(answer="done", error=None)

    async def stream(self, *, from_index: int = 0, **_kwargs: object):
        for event in self._events[from_index:]:
            yield event


class _FakeSdkClient:
    def __init__(self, handle: _FakeHandle) -> None:
        self._handle = handle
        self.requests: list[dict[str, object]] = []

    async def start_session(self, **create_params: object) -> _FakeHandle:
        self.requests.append(create_params)
        return self._handle


@pytest.fixture()
def wired(monkeypatch: pytest.MonkeyPatch) -> tuple[AgentApiClient, _FakeHandle, _FakeSdkClient]:
    handle = _FakeHandle(events=[_FernishEvent(), _FernishEvent()])
    sdk = _FakeSdkClient(handle)
    monkeypatch.setattr(client_module, "AsyncClient", SimpleNamespace(local=lambda *, runtime=None, **_ignored: sdk))
    return AgentApiClient(SimpleNamespace(base_url="http://127.0.0.1:18795")), handle, sdk


def test_create_session_passes_the_holo_request_through(wired) -> None:
    api, _handle, sdk = wired
    request = build_session_request(task="do it", max_steps=7, max_time_s=60.0, idle_timeout_s=120)

    session_id = asyncio.run(api.create_session(request))

    assert session_id == "s-1"
    # The SDK's start_session takes create_session kwargs; the request content
    # must reach it unmodified (same wire dump the old client POSTed directly).
    assert sdk.requests == [request.model_dump(mode="json", exclude_none=True)]


def test_session_verbs_route_to_the_created_handle(wired) -> None:
    api, handle, _sdk = wired

    async def flow() -> None:
        session_id = await api.create_session(build_session_request(task="t", max_steps=None, max_time_s=None))
        await api.send_message(session_id, "more")
        await api.pause(session_id)
        await api.cancel(session_id)

    asyncio.run(flow())

    assert handle.sent == ["more"]
    assert handle.paused == 1
    assert handle.cancelled == 1


def test_stream_projection_matches_the_runner_contract(wired) -> None:
    api, _handle, _sdk = wired

    async def flow() -> list[TrajectoryEvent]:
        session_id = await api.create_session(build_session_request(task="t", max_steps=None, max_time_s=None))
        stream = api.stream(session_id, from_index=0)
        seen = [event async for event in stream.events()]
        assert stream.next_index == 2, "resume cursor counts consumed events"
        assert stream.status == TrajectoryStatus.COMPLETED
        assert stream.answer == "done"
        assert stream.error is None
        return seen

    assert len(asyncio.run(flow())) == 2


def test_events_are_normalized_to_agp_trajectory_events(wired) -> None:
    # The runner-side helpers (events.is_answer, feed rendering, acp/mcp
    # translation) require agp TrajectoryEvent with dict data; SDK events carry
    # typed pydantic payloads and must be flattened back.
    api, _handle, _sdk = wired

    async def flow() -> list[TrajectoryEvent]:
        session_id = await api.create_session(build_session_request(task="t", max_steps=None, max_time_s=None))
        return [event async for event in api.stream(session_id, from_index=0).events()]

    seen = asyncio.run(flow())
    assert all(isinstance(event, TrajectoryEvent) for event in seen)
    assert all(isinstance(event.data, dict) for event in seen)
    assert events_module.is_answer(seen[0]), "the flattened payload must parse as the typed answer event"
    assert events_module.answer_text(seen[0]) == "done"


def test_unknown_terminal_status_projects_as_failed(wired, monkeypatch: pytest.MonkeyPatch) -> None:
    # Rehomed from the old client's _coerce_status: an unknown *terminal* status
    # must end the turn as FAILED with an explanatory error, never crash the
    # projection or report a phantom success.
    api, handle, _sdk = wired
    handle._status = "exploded"

    async def flow() -> None:
        session_id = await api.create_session(build_session_request(task="t", max_steps=None, max_time_s=None))
        stream = api.stream(session_id, from_index=0)
        async for _ in stream.events():
            pass
        assert stream.status == TrajectoryStatus.FAILED
        assert stream.error is not None and "exploded" in stream.error

    asyncio.run(flow())


def test_dead_session_api_errors_translate_to_httpx(wired) -> None:
    # session_runner._create_or_continue (frozen spec) recreates the session on
    # httpx.HTTPStatusError with 404/409/410; SDK ApiErrors must surface as that.
    api, handle, _sdk = wired
    handle.send_error = ApiError(status_code=404, body="session gone")

    async def flow() -> None:
        session_id = await api.create_session(build_session_request(task="t", max_steps=None, max_time_s=None))
        with pytest.raises(httpx.HTTPStatusError) as excinfo:
            await api.send_message(session_id, "more")
        assert excinfo.value.response.status_code == 404

    asyncio.run(flow())


def test_unknown_session_id_is_rejected(wired) -> None:
    api, _handle, _sdk = wired

    async def flow() -> None:
        with pytest.raises(RuntimeError, match="unknown agent-API session"):
            await api.send_message("nope", "text")

    asyncio.run(flow())
