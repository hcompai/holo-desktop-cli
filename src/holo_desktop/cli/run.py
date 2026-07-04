"""`holo run`: one-shot task driven by the hai-agent-runtime binary over the agent API."""

from __future__ import annotations

import asyncio
import logging
import shutil
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import httpx
import tyro
from hai_agents.local import LocalRuntimeError

if TYPE_CHECKING:
    from rich.console import Console

    from holo_desktop.killswitch.listener import StopListener

from holo_desktop.agent_client import permissions
from holo_desktop.agent_client.sdk_runtime import port_from_env
from holo_desktop.settings import AGENT_API_DEFAULT_PORT, PORT_ENV, HoloSettings

logger = logging.getLogger(__name__)


def run(
    task: Annotated[str, tyro.conf.Positional, tyro.conf.arg(metavar="TASK")],
    quiet: Annotated[bool, tyro.conf.arg(aliases=["-q"])] = False,
    model: str | None = None,
    base_url: str | None = None,
    max_steps: int | None = None,
    max_time_s: float | None = None,
    runs_dir: Annotated[
        Path | None,
        tyro.conf.arg(
            metavar="DIR",
            help="Directory the binary streams per-run JSONL event logs into (binary default: ~/.holo/runs).",
        ),
    ] = None,
    port: Annotated[
        int | None,
        tyro.conf.arg(help=f"Agent-API port; defaults to ${PORT_ENV}, else {AGENT_API_DEFAULT_PORT}."),
    ] = None,
    fake: Annotated[
        bool, tyro.conf.arg(help="Spawn the binary in fake-agent mode (no model/desktop). For testing.")
    ] = False,
    fast: Annotated[
        bool,
        tyro.conf.arg(help="Opt-in fast mode: one screenshot, no thinking, smaller uploads. Faster but lower quality."),
    ] = False,
    profile: Annotated[
        bool, tyro.conf.arg(help="Print per-step observe/llm/tool timings at exit from the runtime event log.")
    ] = False,
    expand: Annotated[
        bool,
        tyro.conf.arg(help="Print every step as a full panel (note/thought/tool) instead of collapsing history."),
    ] = False,
    no_kill_switch: Annotated[
        bool,
        tyro.conf.arg(help="Disable the double-Esc kill switch (skips the macOS Input Monitoring prompt)."),
    ] = False,
) -> None:
    """Run a one-shot foreground task on the visible desktop."""
    # Heavy imports are deferred into the command body to keep `holo --help` fast.
    import logging

    from rich.console import Console
    from rich.panel import Panel
    from rich.text import Text

    from holo_desktop.cli.bootstrap import bootstrap_interactive

    # Per-request HTTP chatter is implementation detail, not user output.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    if quiet:
        logging.getLogger("hai_agents.local").setLevel(logging.WARNING)

    settings = bootstrap_interactive(base_url=base_url, fake=fake)

    # Resolved after load_holo_env so a port set in ~/.holo/.env counts too.
    resolved_port = port if port is not None else port_from_env(settings=settings)

    err = Console(stderr=True)
    out = Console()

    def die(title: str, message: str) -> None:
        err.print(
            Panel(
                Text(message),
                title=f"[bold red]✗[/bold red] {title}",
                title_align="left",
                border_style="red",
                expand=False,
                padding=(0, 2),
            )
        )
        raise SystemExit(1)

    # First task against a freshly downloaded runtime on macOS: TCC prompts appear, grants latch only after restart.
    walkthrough_pending = (
        sys.platform == "darwin"
        and not fake
        and shutil.which("hai-agent-runtime") is None
        and permissions.first_run_pending()
    )
    if walkthrough_pending and not quiet:
        err.print(
            Panel(
                "First run on macOS: when the task starts, macOS will prompt for [bold]Accessibility[/bold] "
                "and [bold]Screen Recording[/bold] for the Holo runtime. Grant both — if the first task "
                "still fails, Holo restarts the runtime once automatically (grants only apply after a restart).",
                title="[bold]macOS permissions[/bold]",
                title_align="left",
                border_style="yellow",
                expand=False,
                padding=(0, 2),
            )
        )

    def attempt() -> tuple[str | None, str | None, str | None, bool, Path | None]:
        """One full session; reports whether this run spawned the runtime, and its stderr log path."""
        try:
            return asyncio.run(
                _drive(
                    task=task,
                    quiet=quiet,
                    model=model,
                    base_url=base_url,
                    max_steps=max_steps,
                    max_time_s=max_time_s,
                    runs_dir=runs_dir,
                    port=resolved_port,
                    fake=fake,
                    fast=fast,
                    profile=profile,
                    expand=expand,
                    settings=settings,
                )
            )
        except KeyboardInterrupt:
            # run_turn cancels the agent-API session as it unwinds; here we only report it.
            err.print("[yellow]✗ interrupted[/yellow] [dim]stopped by user; session cancelled[/dim]")
            raise SystemExit(130) from None

    # Only a real terminal has a human who can press Esc; arming a global listener in a
    # captured/headless subprocess would prompt for permission or crash with no one to use it.
    from holo_desktop.killswitch import is_interactive_tty

    kill_switch = _arm_kill_switch(
        enabled=not no_kill_switch and not fake and is_interactive_tty(), quiet=quiet, err=err
    )
    try:
        answer, status, error, spawned, log_path = attempt()
        # The runtime may surface a TCC failure only via the session error, not its stderr log: check both.
        permission_shaped = permissions.log_tail_suggests_permissions(log_path) or (
            error is not None and permissions.text_suggests_permissions(error)
        )
        if walkthrough_pending and status == "failed" and permission_shaped:
            if spawned:
                err.print(
                    "[yellow]→[/yellow] [dim]permission grants only apply after a runtime restart; "
                    "restarting the runtime and retrying once[/dim]"
                )
                answer, status, error, spawned, log_path = attempt()
            else:
                # Attached runtime: shutdown was a no-op, so a retry reuses the same process and grants stay unlatched.
                err.print(
                    f"[yellow]→[/yellow] [dim]permission grants only apply after a runtime restart, but the "
                    f"runtime on port {resolved_port} was started by another Holo process (e.g. holo serve or "
                    "holo mcp). Restart that process so the grants latch, or pass --port to spawn a fresh "
                    "runtime here.[/dim]"
                )
    except (RuntimeError, LocalRuntimeError, httpx.HTTPError) as exc:
        die(type(exc).__name__, str(exc))
        return
    finally:
        if kill_switch is not None:
            kill_switch.stop()

    if status is None:
        die("agent error", error or "session ended without terminal status")
    if status == "failed":
        die("agent error", error or "unknown failure")
    if status in ("interrupted", "timed_out"):
        die(status, error or f"session {status}")
    if walkthrough_pending:
        permissions.mark_first_run_complete()
    if answer:
        if quiet:
            out.print(Text(answer))
        else:
            out.print(
                Panel(
                    Text(answer),
                    title="[bold green]✓ answer[/bold green]",
                    title_align="left",
                    border_style="green",
                    padding=(0, 2),
                )
            )
    if not quiet:
        err.print(
            Panel(
                "Holo also runs inside your other agents: [cyan]holo install[/cyan] (MCP hosts) · "
                "[cyan]holo acp[/cyan] (ACP hosts) · [cyan]holo serve[/cyan] (A2A server)",
                border_style="dim",
                expand=False,
                padding=(0, 2),
            )
        )


async def _drive(
    *,
    task: str,
    quiet: bool,
    model: str | None,
    base_url: str | None,
    max_steps: int | None,
    max_time_s: float | None,
    runs_dir: Path | None,
    port: int,
    fake: bool,
    fast: bool,
    profile: bool,
    expand: bool,
    settings: HoloSettings,
) -> tuple[str | None, str | None, str | None, bool, Path | None]:
    """Spawn/attach the binary, run one turn, return (answer, status, error, spawned, log_path)."""
    from agp_types import TrajectoryEvent
    from rich.console import Console

    from holo_desktop.agent_client.client import AgentApiClient
    from holo_desktop.agent_client.event_timings import (
        extract_step_timings,
        find_session_event_log,
        render_step_timings,
    )
    from holo_desktop.agent_client.sdk_runtime import SpawnConfig, ensure_local_runtime
    from holo_desktop.agent_client.session_runner import Session, run_turn
    from holo_desktop.terminal.feed import LiveFeed

    console = Console(stderr=True)

    # ensure_local_runtime may download the runtime on first run; keep that off the event loop.
    runtime = await asyncio.to_thread(
        ensure_local_runtime,
        SpawnConfig(port=port, model=model, base_url=base_url, fake=fake, fast=fast, runs_dir=runs_dir),
        settings=settings,
    )
    spawned = runtime.owned
    try:
        async with AgentApiClient(runtime) as client:
            session = Session()
            feed = None if quiet else LiveFeed(console, expand=expand)

            async def render(event: TrajectoryEvent) -> None:
                if feed is not None:
                    try:
                        feed.handle(event)
                    except Exception:
                        logger.warning("failed to render event %s", event.type, exc_info=True)

            try:
                outcome = await run_turn(
                    client, session, task, max_steps=max_steps, max_time_s=max_time_s, on_event=render
                )
            finally:
                if feed is not None:
                    feed.close()
            if profile and session.session_id is not None:
                timing = extract_step_timings(find_session_event_log(runs_dir, session.session_id))
                if timing is not None:
                    # Render even on failure: partial timings are still useful.
                    render_step_timings(timing, console)
            status = outcome.status.value if outcome.status is not None else None
            return outcome.answer, status, outcome.error, spawned, runtime.log_path
    finally:
        # Same semantics as the old daemon.aclose(): stop the runtime only if this run spawned it,
        # which is also what makes the one-shot TCC retry respawn a fresh process.
        if runtime.owned:
            await asyncio.to_thread(runtime.shutdown)


def _arm_kill_switch(*, enabled: bool, quiet: bool, err: Console) -> StopListener | None:
    """Arm the double-Esc kill switch and render its outcome; returns the listener to stop later, or None."""
    from holo_desktop.killswitch import (
        KILL_SWITCH_ARMED_HINT,
        KILL_SWITCH_UNAVAILABLE_HINT,
        ArmOutcome,
        arm_stop_listener,
    )

    listener, outcome = arm_stop_listener(enabled=enabled)
    if outcome is ArmOutcome.UNAVAILABLE:
        # A panic button that silently fails to arm is dangerous; always say so, even when quiet.
        err.print(f"[yellow]⚠ {KILL_SWITCH_UNAVAILABLE_HINT}[/yellow]")
    elif outcome is ArmOutcome.ARMED and not quiet:
        err.print(f"[dim]{KILL_SWITCH_ARMED_HINT}[/dim]")
    return listener
