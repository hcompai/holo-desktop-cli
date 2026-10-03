"""Build the ``SessionRequest`` the client sends to the binary from ``~/.holo``."""

from __future__ import annotations

from agent_interface.specs.agent import Agent
from agent_interface.specs.environment import Desktop
from agent_interface.specs.session import SessionRequest
from agent_interface.specs.skill import Skill

from holo_desktop import customization

HOLO_AGENT_NAME = "holo"
HOLO_AGENT_DESCRIPTION = "Desktop agent that drives the user's machine via H Company's shared agent recipe."
# The SDK binds this inline device specification to its owned local executor.
DESKTOP_ENVIRONMENT_ID = "desktop"


def build_session_request(
    *, task: str, max_steps: int | None, max_time_s: float | None, idle_timeout_s: int | None = None
) -> SessionRequest:
    """Compose the session request: an inline ``Agent`` carrying ``~/.holo`` inputs plus the task."""
    ctx = customization.load_agent_context()
    instructions = customization.render_instructions(ctx)
    skills: list[str | Skill] = [*ctx.skills]
    agent = Agent(
        name=HOLO_AGENT_NAME,
        description=HOLO_AGENT_DESCRIPTION,
        environments=[Desktop(id=DESKTOP_ENVIRONMENT_ID, host="user_device")],
        model=None,  # spawn-time HAI_AGENT_RUNTIME_MODEL wins, no per-request override
        reasoning_effort=None,
        instructions=instructions or None,
        subagents=None,
        skills=skills or None,
        tools=None,
    )
    return SessionRequest(
        agent=agent,
        messages=task,
        max_steps=max_steps,
        max_time_s=max_time_s,
        idle_timeout_s=idle_timeout_s,
    )
