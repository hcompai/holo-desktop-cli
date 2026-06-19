"""`holo install`: wire one or every detected MCP host."""

from typing import Annotated

import tyro
from rich.console import Console

from holo_desktop.cli.hosts import (
    CLIENTS,
    Status,
    home_short,
    host_present,
    host_target,
    resolve_holo_command,
    wire_host,
    wire_skill,
)
from holo_desktop.killswitch.autostart import AutostartResult, ensure_autostart

err = Console(stderr=True)

STYLE: dict[Status, tuple[str, str]] = {
    Status.INSTALLED: ("[bold green]✓[/bold green]", "dim"),
    Status.SKIPPED: ("[dim green]·[/dim green]", "dim"),
    Status.ABSENT: ("[yellow]⊘[/yellow]", "yellow"),
    Status.FAILED: ("[bold red]✗[/bold red]", "red"),
}
_GUARD_STATUS: dict[AutostartResult, Status] = {
    AutostartResult.INSTALLED: Status.INSTALLED,
    AutostartResult.SKIPPED: Status.SKIPPED,
    AutostartResult.UNSUPPORTED: Status.ABSENT,
    AutostartResult.FAILED: Status.FAILED,
}
ID_WIDTH = max(len(host_id) for host_id in CLIENTS)

# `holo install` wires the MCP server into hosts for you; these are the raw stdio
# servers a host config invokes. Typing them as an install target is a common slip.
PROTOCOL_WORDS = ("mcp", "acp")


def install(
    client: Annotated[str | None, tyro.conf.Positional, tyro.conf.arg(metavar="CLIENT")] = None,
) -> None:
    """Wire Holo into an MCP host: merge MCP config + symlink the SKILL.md."""
    if client in PROTOCOL_WORDS:
        err.print(
            f"[bold red]✗[/bold red] [bold cyan]holo install[/bold cyan] wires the MCP server into a host's "
            f"config for you — it takes a host id, not [yellow]{client!r}[/yellow].\n"
            f"  • to wire a host:        [cyan]holo install <host>[/cyan]  (see [cyan]holo install list[/cyan])\n"
            f"  • to run the raw server: [cyan]holo {client}[/cyan]  (what a host config invokes under the hood)"
        )
        raise SystemExit(2)

    if client == "list":
        err.print()
        for host_id, c in CLIENTS.items():
            glyph = "[green]✓[/green]" if host_present(c) else "[dim]·[/dim]"
            err.print(f"  {glyph} [bold cyan]{host_id:<{ID_WIDTH}}[/bold cyan]  [dim]{host_target(c)}[/dim]")
        err.print()
        err.print("  [dim]✓ = detected on this machine ·  wire with[/dim] [cyan]holo install <id>[/cyan]")
        err.print()
        return

    if client is None:
        targets = [(host_id, c) for host_id, c in CLIENTS.items() if host_present(c)]
        if not targets:
            err.print(
                "[yellow]No supported hosts detected under $HOME.[/yellow] "
                "Run [cyan]holo install list[/cyan] to see what's supported."
            )
            raise SystemExit(1)
    elif client in CLIENTS:
        targets = [(client, CLIENTS[client])]
    else:
        err.print(
            f"[bold red]✗[/bold red] unknown host {client!r}. "
            f"Run [cyan]holo install list[/cyan] to see what's supported."
        )
        raise SystemExit(2)

    err.print()
    failed = False
    for host_id, c in targets:
        status, detail = wire_host(c)
        glyph, color = STYLE[status]
        line = f"  {glyph} [bold cyan]{host_id:<{ID_WIDTH}}[/bold cyan]  [{color}]{detail}[/{color}]"
        skill_fatal = False
        if c.wire is None and c.skills_dir is not None:
            s_status, s_detail = wire_skill(c)
            skill_fatal = s_status.fatal
            if s_status.ok:
                line += f"  [dim]→ {s_detail}[/dim]"
            else:
                s_glyph, s_color = STYLE[s_status]
                line += f"  {s_glyph} [{s_color}]{s_detail}[/{s_color}]"
        err.print(line)
        failed |= status.fatal or skill_fatal
    _install_guard()
    err.print()
    if failed:
        raise SystemExit(1)


def _install_guard() -> None:
    """Best-effort: set up the always-on double-Esc kill switch as an OS autostart service."""
    label = "kill-switch"
    try:
        result, detail = ensure_autostart(resolve_holo_command())
    except RuntimeError as exc:
        glyph, color = STYLE[Status.FAILED]
        err.print(f"  {glyph} [bold cyan]{label:<{ID_WIDTH}}[/bold cyan]  [{color}]{exc}[/{color}]")
        return
    glyph, color = STYLE[_GUARD_STATUS[result]]
    err.print(f"  {glyph} [bold cyan]{label:<{ID_WIDTH}}[/bold cyan]  [{color}]{home_short(detail)}[/{color}]")
