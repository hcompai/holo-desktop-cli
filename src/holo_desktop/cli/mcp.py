"""`holo mcp`: stdio MCP server exposing the local desktop agent as one tool."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from agp_types import TrajectoryEvent
from hai_agents import AsyncClient
from mcp.server.fastmcp import Context, FastMCP

from holo_desktop import __version__
from holo_desktop.cli.bootstrap import bootstrap_stdio
from holo_desktop.events import format_event
from holo_desktop.task import SUCCESS_STATUSES, build_agent, open_client, resolve_target, run_task

INSTRUCTIONS = (
    "Sub-agent that drives the user's desktop via H Company's Holo vision-language model, "
    "using the real cursor and keyboard in the foreground. Call `holo_desktop` for goals that require operating a native UI "
    "the caller cannot reach: opening apps (Slack, Mail, Calendar, Authy, Obsidian), filling "
    "forms, controlling the user's logged-in Chrome session, toggling system settings. Do not "
    "use it for tasks you can already do (file edits, web fetches, terminal commands). Holo is "
    "blind to the rest of the conversation, so the `task` string must be self-contained: fold in "
    "the context the user implied (which workspace, who 'Sarah' is, what counts as done), while "
    "preserving their action verbs and any message text verbatim. One task runs at a time per machine."
)
# Tool calls queue here: the SDK hands this process's desktop to the newest session, which would cut off the running one.
_one_task_at_a_time = asyncio.Lock()


@asynccontextmanager
async def lifespan(_: FastMCP) -> AsyncIterator[AsyncClient]:
    base_url, model = resolve_target()
    client = await open_client(base_url=base_url, model=model)
    try:
        yield client
    finally:
        await client.aclose()


mcp_app = FastMCP("holo-desktop", instructions=INSTRUCTIONS, lifespan=lifespan, log_level="WARNING")
mcp_app._mcp_server.version = __version__


@mcp_app.tool()
async def holo_desktop(task: str, ctx: Context) -> str:
    """Run a desktop task on the user's local machine. Pass `task` verbatim. Blocks until completion."""
    task = task.strip()
    if not task:
        raise ValueError("task must not be blank")
    client: AsyncClient = ctx.request_context.lifespan_context

    started = asyncio.get_running_loop().time()
    steps = 0

    async def forward(event: TrajectoryEvent) -> None:
        nonlocal steps
        line = format_event(event)
        if line is not None:
            await ctx.info(line)
            steps += 1
            await ctx.report_progress(progress=float(steps), message=f"step {steps}")

    _, model = resolve_target()
    async with _one_task_at_a_time:
        outcome = await run_task(
            client, build_agent(model=model), task, max_steps=None, max_time_s=None, on_event=forward
        )

    elapsed = round(asyncio.get_running_loop().time() - started, 2)
    if outcome.status in SUCCESS_STATUSES:
        return outcome.answer or "(empty answer)"
    if outcome.status == "failed":
        raise RuntimeError(f"holo error: {outcome.error or 'unknown failure'}")
    if outcome.status == "timed_out":
        raise RuntimeError(f"holo timed out: {outcome.error or 'step/time budget exhausted'}")
    return f"(session ended as {outcome.status} after {steps} step(s), {elapsed}s)"


def mcp() -> None:
    """Run as a stdio MCP server. Starts the local runtime if none is listening."""
    bootstrap_stdio()
    mcp_app.run()
