"""Build the ``SessionRequest`` the client sends to the binary from ``~/.holo``."""

from __future__ import annotations

from agent_interface.specs.agent import Agent
from agent_interface.specs.session import SessionRequest
from agent_interface.specs.skill import Skill

from holo_desktop import customization

HOLO_AGENT_NAME = "holo"
HOLO_AGENT_DESCRIPTION = "Desktop agent that drives the user's machine via H Company's Holo3 VLM."
# Catalog id only: the spec requires a non-empty `environments` list, but the binary pins the desktop environment per process and never resolves this entry.
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
        environments=[DESKTOP_ENVIRONMENT_ID],
        model=None,  # spawn-time HAI_AGENT_RUNTIME_MODEL wins, no per-request override
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
