"""Core task rules: events stream through, interruptions cancel the session, outcomes map to tool results."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from agent_interface.specs.skill import Skill
from agp_types import TrajectoryEvent

from holo_desktop import customization
from holo_desktop.cli.mcp import holo_desktop
from holo_desktop.task import DEFAULT_MAX_STEPS, Outcome, build_agent, run_task

EVENT = TrajectoryEvent(
    type="AgentEvent", data={"kind": "policy_event", "content": "thinking"}, timestamp=datetime.now(UTC)
)


@pytest.fixture(autouse=True)
def _user_context(monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = customization.AgentContext(
        agents_md="Prefer keyboard shortcuts.",
        memories=(),
        rules=(),
        skills=(Skill(name="demo", description="A demo skill.", body="Do the demo."),),
    )
    monkeypatch.setattr(customization, "load_agent_context", lambda: ctx)


@dataclass
class FakeHandle:
    status: str = "completed"
    answer: str | None = "done"
    error: str | None = None
    cancelled: bool = False

    async def stream(self) -> AsyncIterator[TrajectoryEvent]:
        yield EVENT

    async def wait_for_completion(self) -> SimpleNamespace:
        return SimpleNamespace(status=self.status, answer=self.answer, error=self.error)

    async def cancel(self) -> None:
        self.cancelled = True


@dataclass
class FakeClient:
    handle: FakeHandle = field(default_factory=FakeHandle)
    requests: list[dict[str, Any]] = field(default_factory=list)

    async def start_session(self, **kwargs: Any) -> FakeHandle:
        self.requests.append(kwargs)
        return self.handle


def _run(client: FakeClient, on_event: Any) -> Outcome:
    return asyncio.run(
        run_task(client, build_agent(), "do it", max_steps=None, max_time_s=None, on_event=on_event)  # type: ignore[arg-type]
    )


def test_run_task_streams_events_and_returns_the_outcome() -> None:
    client = FakeClient()
    seen: list[TrajectoryEvent] = []

    async def collect(event: TrajectoryEvent) -> None:
        seen.append(event)

    assert _run(client, collect) == Outcome(status="completed", answer="done", error=None)
    assert [event.type for event in seen] == ["AgentEvent"]
    assert client.requests[0]["messages"] == "do it"
    assert client.requests[0]["max_steps"] == DEFAULT_MAX_STEPS


def test_interrupted_task_cancels_the_session() -> None:
    client = FakeClient()

    async def interrupt(event: TrajectoryEvent) -> None:
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        _run(client, interrupt)
    assert client.handle.cancelled


def test_agent_carries_user_customization_and_fast_disables_reasoning() -> None:
    default = build_agent().model_dump(mode="json", exclude_unset=True)
    assert "reasoning_effort" not in default
    assert "model" not in default
    assert "Prefer keyboard shortcuts." in default["instructions"]
    assert [skill["name"] for skill in default["skills"]] == ["demo"]
    assert default["environments"] == [{"id": "desktop", "kind": "desktop", "host": "user_device"}]
    fast = build_agent(model="holo4-35b-a3b", fast=True)
    assert (fast.reasoning_effort, fast.model) == ("disabled", "holo4-35b-a3b")


def _call_tool(handle: FakeHandle) -> str:
    async def note(*args: Any, **kwargs: Any) -> None:
        pass

    ctx = SimpleNamespace(
        request_context=SimpleNamespace(lifespan_context=FakeClient(handle)), info=note, report_progress=note
    )
    return asyncio.run(holo_desktop("do it", ctx))


def test_mcp_tool_returns_the_answer_and_raises_on_failure() -> None:
    assert _call_tool(FakeHandle()) == "done"
    with pytest.raises(RuntimeError, match="budget exhausted"):
        _call_tool(FakeHandle(status="timed_out", answer=None, error="budget exhausted"))
    with pytest.raises(RuntimeError, match="holo error: boom"):
        _call_tool(FakeHandle(status="failed", answer=None, error="boom"))


def test_mcp_server_reports_the_cli_version() -> None:
    from holo_desktop import __version__
    from holo_desktop.cli.mcp import mcp_app

    assert mcp_app._mcp_server.create_initialization_options().server_version == __version__
