"""One desktop task on this machine, through the hai-agents SDK's local runtime."""

from __future__ import annotations

import asyncio
import contextlib
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from agp_types import TrajectoryEvent
from hai_agents import Agent, AsyncClient
from hai_agents_local.desktop_lock import DesktopBusyError
from hai_agents_local.runtime import Inference

from holo_desktop import customization

BASE_URL_ENV = "HAI_AGENT_RUNTIME_BASE_URL"
MODEL_ENV = "HAI_AGENT_RUNTIME_MODEL"
DEFAULT_MAX_STEPS = 150
DEFAULT_MAX_TIME_S = 1800.0
SUCCESS_STATUSES = frozenset({"completed", "idle"})
DESKTOP_BUSY = "another agent is driving this desktop; wait for it to finish or stop it with `holo stop`"


@dataclass(frozen=True)
class Outcome:
    status: str
    answer: str
    error: str | None


def build_agent(*, model: str | None = None, fast: bool = False) -> Agent:
    """The inline desktop agent, carrying the user's `~/.holo` instructions and skills."""
    ctx = customization.load_agent_context()
    optional = {
        "instructions": customization.render_instructions(ctx),
        "skills": [skill.model_dump(mode="json", exclude_none=True) for skill in ctx.skills],
        "model": model,
        "reasoning_effort": "disabled" if fast else None,
    }
    return Agent.model_validate(
        {
            "name": "holo",
            "description": "Desktop agent that drives the user's machine.",
            "environments": [{"id": "desktop", "kind": "desktop", "host": "user_device"}],
            **{key: value for key, value in optional.items() if value},
        }
    )


def resolve_target(base_url: str | None = None, model: str | None = None) -> tuple[str | None, str | None]:
    """Self-hosted endpoint and model: explicit values, else `HAI_AGENT_RUNTIME_BASE_URL` / `_MODEL`."""
    return base_url or os.environ.get(BASE_URL_ENV) or None, model or os.environ.get(MODEL_ENV) or None


async def open_client(*, base_url: str | None = None, model: str | None = None) -> AsyncClient:
    """A client on the local runtime; `base_url` points inference at a self-hosted server named `model`."""
    inference = Inference.self_hosted(base_url, model=model or "") if base_url else None
    return await AsyncClient.local(inference=inference)


async def run_task(
    client: AsyncClient,
    agent: Agent,
    task: str,
    *,
    max_steps: int | None,
    max_time_s: float | None,
    on_event: Callable[[TrajectoryEvent], Awaitable[None]],
) -> Outcome:
    """Run `task` until it settles, streaming each event to `on_event`, then end the session either way."""
    try:
        handle = await client.start_session(
            agent=agent,
            messages=task,
            max_steps=max_steps or DEFAULT_MAX_STEPS,
            max_time_s=max_time_s or DEFAULT_MAX_TIME_S,
        )
    except RuntimeError as exc:
        if isinstance(exc.__cause__, DesktopBusyError):
            raise DesktopBusyError(DESKTOP_BUSY) from exc
        raise
    try:
        async for event in handle.stream():
            await on_event(TrajectoryEvent.model_validate(event.model_dump(mode="json")))
        result = await handle.wait_for_completion()
    finally:
        # A one-shot task that settles idle would otherwise keep its bridge, and the machine's desktop claim.
        with contextlib.suppress(Exception):
            await asyncio.shield(handle.cancel())
    answer = "" if result.answer is None else result.answer if isinstance(result.answer, str) else str(result.answer)
    return Outcome(status=str(result.status), answer=answer, error=result.error)
