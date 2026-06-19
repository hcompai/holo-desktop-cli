"""`holo stop`: signal the running Holo turn to stop, optionally force-killing the runtime."""

from __future__ import annotations

import time
from typing import Annotated

import tyro


def stop(
    force: Annotated[
        bool,
        tyro.conf.arg(
            help="Also SIGKILL the hai-agent-runtime process: instant, but ends the session outright. "
            "Caveat: a runtime that died uncleanly can leave a stale pid file, so this may target a recycled pid."
        ),
    ] = False,
    port: Annotated[
        int | None,
        tyro.conf.arg(help="Runtime port to force-kill; defaults to every spawned runtime found."),
    ] = None,
) -> None:
    """Ask any in-flight Holo turn to pause then cancel (the same effect as the double-Esc kill switch)."""
    from rich.console import Console

    from holo_desktop.agent_client.launcher import discover_runtime_pids, kill_runtime_by_pid
    from holo_desktop.killswitch.channel import request_stop

    out = Console(stderr=True)
    request_stop(time.time())
    out.print("[yellow]■ stop requested[/yellow] [dim]any running Holo turn will pause then cancel[/dim]")

    if not force:
        return

    killed = [pid for pid in discover_runtime_pids(port) if kill_runtime_by_pid(pid)]
    if killed:
        out.print(f"[red]✗ force-killed runtime[/red] [dim]pid(s) {', '.join(map(str, killed))}[/dim]")
    else:
        out.print("[dim]no spawned runtime process found to force-kill[/dim]")
