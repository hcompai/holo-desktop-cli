"""`holo stop`: signal the running Holo turn to stop, optionally force-killing the runtime."""

from __future__ import annotations

import time
from typing import Annotated

import tyro
from hai_agents.local import LocalRuntime


def stop(
    force: Annotated[
        bool,
        tyro.conf.arg(
            help="Also SIGKILL the hai-agent-runtime process: instant, but ends the session outright."
        ),
    ] = False,
    port: Annotated[
        int | None,
        tyro.conf.arg(
            help="Runtime port to force-kill; defaults to the default port plus any legacy pid files."
        ),
    ] = None,
) -> None:
    """Ask any in-flight Holo turn to pause then cancel (the same effect as the double-Esc kill switch)."""
    from rich.console import Console

    from holo_desktop.agent_client.legacy_state import legacy_force_kill
    from holo_desktop.killswitch.channel import request_stop

    out = Console(stderr=True)
    request_stop(time.time())
    out.print("[yellow]■ stop requested[/yellow] [dim]any running Holo turn will pause then cancel[/dim]")

    if not force:
        return

    killed: list[int] = []
    # force_kill is a runtime-process kill, not a session kill — the same semantics
    # as the old pid-file SIGKILL. attach() reads SDK discovery state, so it finds a
    # hung-but-alive runtime even when /health would fail.
    runtime = LocalRuntime.attach(port=port)
    if runtime is not None and runtime.pid is not None:
        runtime.force_kill()
        killed.append(runtime.pid)
    # One-release compat: runtimes spawned by a pre-SDK holo (see legacy_state docstring).
    killed += legacy_force_kill(port)
    if killed:
        out.print(f"[red]✗ force-killed runtime[/red] [dim]pid(s) {', '.join(map(str, killed))}[/dim]")
    else:
        out.print("[dim]no spawned runtime process found to force-kill[/dim]")
