"""`holo guard`: the always-on double-Esc kill switch, for hosts (`holo mcp`) with no terminal of their own."""

from __future__ import annotations

import logging
import sys
import time


def guard() -> None:
    """Listen for a rapid double Esc and cancel any running Holo task, until Ctrl+C."""
    from rich.console import Console

    from holo_desktop import killswitch

    logging.basicConfig(level=logging.WARNING, stream=sys.stderr, format="%(levelname)s %(name)s: %(message)s")
    err = Console(stderr=True)

    listener = killswitch.arm()
    if listener is None:
        err.print(f"[bold red]✗ could not start the kill switch.[/bold red] {killswitch.UNAVAILABLE_HINT}")
        raise SystemExit(1)

    err.print(
        "[bold green]● Holo kill switch active[/bold green] [dim]press Esc twice fast to stop any "
        "running Holo task; Ctrl+C to quit[/dim]"
    )
    # A timeout loop, not a bare wait(): only periodic returns to the interpreter let Ctrl+C land promptly.
    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        err.print("[dim]kill switch stopped[/dim]")
    finally:
        listener.stop()
