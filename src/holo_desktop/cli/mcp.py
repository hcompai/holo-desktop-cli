"""`holo mcp`: stdio MCP server exposing the local desktop agent as one tool."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from agp_types import TrajectoryEvent, TrajectoryStatus
from hai_agents.local import LocalRuntime
from mcp.server.fastmcp import Context, FastMCP

from holo_desktop.agent_client.client import AgentApiClient
from holo_desktop.agent_client.events import format_event
from holo_desktop.agent_client.sdk_runtime import ensure_local_runtime_from_env
from holo_desktop.agent_client.session_runner import (
    DEFAULT_MAX_STEPS,
    DEFAULT_MAX_TIME_S,
    SUCCESSFUL_TURN_STATUSES,
    Session,
    cancel_session_best_effort,
    run_turn,
)
from holo_desktop.cli.bootstrap import bootstrap_stdio

INSTRUCTIONS = (
    "Sub-agent that binds to one OS window per task and drives it via H Company's Holo3 "
    "vision-language model. Call `holo_desktop` for goals that require operating a native UI "
    "the caller cannot reach: opening apps (Slack, Mail, Calendar, Authy, Obsidian), filling "
    "forms, controlling the user's logged-in Chrome session, toggling system settings. Do not "
    "use it for tasks you can already do (file edits, web fetches, terminal commands). Holo is "
    "blind to the rest of the conversation, so the `task` string must be self-contained: fold in "
    "the context the user implied (which workspace, who 'Sarah' is, what counts as done), while "
    "preserving their action verbs and any message text verbatim. One task runs at a time per machine."
)


@dataclass
class Lifespan:
    client: AgentApiClient
    runtime: LocalRuntime
    active_session: Session | None = None


@asynccontextmanager
async def lifespan(_: FastMCP) -> AsyncIterator[Lifespan]:
    # ensure_local_runtime_from_env may download the runtime on first run; keep that off the event loop.
    runtime = await asyncio.to_thread(ensure_local_runtime_from_env)
    client = AgentApiClient(runtime)
    state = Lifespan(client=client, runtime=runtime)
    try:
        yield state
    finally:
        await _cancel_active_sessions_best_effort(state)
        await client.aclose()
        # Stop the runtime only if this server spawned it; attached runtimes belong to their spawner.
        if runtime.owned:
            await asyncio.to_thread(runtime.shutdown)


mcp_app = FastMCP("holo-desktop", instructions=INSTRUCTIONS, lifespan=lifespan)


@mcp_app.tool()
async def holo_desktop(task: str, ctx: Context) -> str:
    """Run a desktop task on the user's local machine. Pass `task` verbatim. Blocks until completion."""
    task = task.strip()
    if not task:
        raise ValueError("task must not be blank")
    state: Lifespan = ctx.request_context.lifespan_context

    started = asyncio.get_running_loop().time()
    steps = 0

    async def forward(event: TrajectoryEvent) -> None:
        nonlocal steps
        line = format_event(event)
        if line is not None:
            await ctx.info(line)
            steps += 1
            await ctx.report_progress(progress=float(steps), message=f"step {steps}")

    # One fresh agent-API session per tool call; no cross-call continuity.
    session = Session()
    state.active_session = session
    try:
        outcome = await run_turn(
            state.client, session, task, max_steps=DEFAULT_MAX_STEPS, max_time_s=DEFAULT_MAX_TIME_S, on_event=forward
        )
    finally:
        if state.active_session is session:
            state.active_session = None

    elapsed = round(asyncio.get_running_loop().time() - started, 2)
    if outcome.status in SUCCESSFUL_TURN_STATUSES:
        return outcome.answer or "(empty answer)"
    if outcome.status == TrajectoryStatus.FAILED:
        raise RuntimeError(f"holo error: {outcome.error or 'unknown failure'}")
    if outcome.status == TrajectoryStatus.TIMED_OUT:
        raise RuntimeError(f"holo timed out: {outcome.error or 'step/time budget exhausted'}")
    return f"(session ended as {outcome.status} after {steps} step(s), {elapsed}s)"


async def _cancel_active_sessions_best_effort(state: Lifespan) -> None:
    if state.active_session is not None:
        await cancel_session_best_effort(state.client, state.active_session)
        state.active_session = None


def mcp() -> None:
    """Run as a stdio MCP server. Auto-spawns the hai-agent-runtime binary if none is listening."""
    bootstrap_stdio("holo-mcp")
    mcp_app.run()
