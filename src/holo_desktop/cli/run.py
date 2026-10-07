"""`holo run`: one foreground desktop task on this machine."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Annotated

import httpx
import tyro
from hai_agents.core.api_error import ApiError

from holo_desktop.task import DEFAULT_MAX_STEPS, DEFAULT_MAX_TIME_S, SUCCESS_STATUSES, Outcome

if TYPE_CHECKING:
    from rich.console import Console

logger = logging.getLogger(__name__)

API_KEY_ERROR_HINTS = ("unauthorized", "invalid api key", "api key is required", "authenticationfailed")


def run(
    task: Annotated[str, tyro.conf.Positional, tyro.conf.arg(metavar="TASK")],
    quiet: Annotated[bool, tyro.conf.arg(aliases=["-q"])] = False,
    model: Annotated[
        str | None, tyro.conf.arg(help="Model to drive the desktop; defaults to $HAI_AGENT_RUNTIME_MODEL.")
    ] = None,
    base_url: Annotated[
        str | None,
        tyro.conf.arg(
            help="Self-hosted OpenAI-compatible server (needs --model); defaults to $HAI_AGENT_RUNTIME_BASE_URL."
        ),
    ] = None,
    max_steps: Annotated[int | None, tyro.conf.arg(help=f"Step budget (default {DEFAULT_MAX_STEPS}).")] = None,
    max_time_s: Annotated[
        float | None, tyro.conf.arg(help=f"Time budget in seconds (default {DEFAULT_MAX_TIME_S:.0f}).")
    ] = None,
    fast: Annotated[bool, tyro.conf.arg(help="Disable model reasoning: faster, lower quality.")] = False,
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
    from rich.console import Console
    from rich.panel import Panel
    from rich.text import Text

    from holo_desktop import killswitch
    from holo_desktop.cli.bootstrap import bootstrap_interactive
    from holo_desktop.task import resolve_target

    logging.getLogger("httpx").setLevel(logging.WARNING)
    bootstrap_interactive(base_url=base_url)
    base_url, model = resolve_target(base_url, model)

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

    listener = None
    if not no_kill_switch and killswitch.is_interactive_tty():
        listener = killswitch.arm()
        if listener is None:
            # A panic button that silently fails to arm is dangerous; always say so, even when quiet.
            err.print(f"[yellow]⚠ {killswitch.UNAVAILABLE_HINT}[/yellow]")
        elif not quiet:
            err.print(f"[dim]{killswitch.ARMED_HINT}[/dim]")
    try:
        outcome = asyncio.run(
            _drive(
                task,
                quiet=quiet,
                model=model,
                base_url=base_url,
                max_steps=max_steps,
                max_time_s=max_time_s,
                fast=fast,
                expand=expand,
                console=err,
            )
        )
    except KeyboardInterrupt:
        err.print("[yellow]✗ interrupted[/yellow] [dim]stopped by user; session cancelled[/dim]")
        raise SystemExit(130) from None
    except PermissionError as exc:
        die("permission denied", str(exc))
        return
    except (RuntimeError, ValueError, httpx.HTTPError, ApiError) as exc:
        die(type(exc).__name__, str(exc))
        return
    finally:
        if listener is not None:
            listener.stop()

    if outcome.status == "failed":
        error = outcome.error or "unknown failure"
        if not base_url and any(hint in error.lower() for hint in API_KEY_ERROR_HINTS):
            die("API key rejected", f"{error}\nRun `holo login --force` to issue a fresh key.")
        die("agent error", error)
    if outcome.status not in SUCCESS_STATUSES:
        die(outcome.status, outcome.error or f"session {outcome.status}")
    if outcome.answer:
        if quiet:
            out.print(Text(outcome.answer))
        else:
            out.print(
                Panel(
                    Text(outcome.answer),
                    title="[bold green]✓ answer[/bold green]",
                    title_align="left",
                    border_style="green",
                    padding=(0, 2),
                )
            )
    if not quiet:
        err.print(
            Panel(
                "Holo also runs inside your other agents: [cyan]holo install[/cyan] (MCP hosts)",
                border_style="dim",
                expand=False,
                padding=(0, 2),
            )
        )


async def _drive(
    task: str,
    *,
    quiet: bool,
    model: str | None,
    base_url: str | None,
    max_steps: int | None,
    max_time_s: float | None,
    fast: bool,
    expand: bool,
    console: Console,
) -> Outcome:
    from agp_types import TrajectoryEvent

    from holo_desktop.task import build_agent, open_client, run_task
    from holo_desktop.terminal.feed import LiveFeed

    feed = None if quiet else LiveFeed(console, expand=expand)

    async def render(event: TrajectoryEvent) -> None:
        if feed is not None:
            try:
                feed.handle(event)
            except Exception:
                logger.warning("failed to render event %s", event.type, exc_info=True)

    client = await open_client(base_url=base_url, model=model)
    try:
        return await run_task(
            client,
            build_agent(model=model, fast=fast),
            task,
            max_steps=max_steps,
            max_time_s=max_time_s,
            on_event=render,
        )
    finally:
        if feed is not None:
            feed.close()
        await client.aclose()
