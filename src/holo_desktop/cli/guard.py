"""`holo guard`: run the always-on double-Esc kill switch in the foreground.

Covers headless surfaces (`holo mcp` under a host, `holo serve`) where no interactive Holo process
exists to host a listener, and where macOS attributes Input Monitoring to the launching app.
"""

from __future__ import annotations

import logging
import sys
import time


def guard() -> None:
    """Listen for a rapid Esc gesture and file a stop request until interrupted (Ctrl+C)."""
    from rich.console import Console

    from holo_desktop.killswitch.listener import StopListener

    logging.basicConfig(level=logging.WARNING, stream=sys.stderr, format="%(levelname)s %(name)s: %(message)s")
    err = Console(stderr=True)

    listener = StopListener()
    if not listener.start():
        err.print(
            "[bold red]✗ could not start the kill switch.[/bold red] On macOS, grant "
            "[bold]Input Monitoring[/bold] to this terminal in System Settings → Privacy & Security, then re-run."
        )
        raise SystemExit(1)

    err.print(
        "[bold green]● Holo kill switch active[/bold green] [dim]press Esc twice fast to stop any "
        "running Holo task; Ctrl+C to quit[/dim]"
    )
    # Park the main thread in a timeout loop, not a bare wait(): only a loop that periodically
    # returns to the interpreter lets a Ctrl+C signal land promptly across platforms.
    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        err.print("[dim]kill switch stopped[/dim]")
    finally:
        listener.stop()
