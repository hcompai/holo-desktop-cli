"""`holo agent-api`: spawn the hai-agent-runtime through the SDK and tail its log."""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import tyro

from holo_desktop.settings import AGENT_API_DEFAULT_PORT, load_holo_settings

if TYPE_CHECKING:
    from rich.console import Console


def agent_api(
    port: int = AGENT_API_DEFAULT_PORT,
    model: str | None = None,
    base_url: str | None = None,
    fake: Annotated[bool, tyro.conf.arg(help="Run the binary in fake-agent mode (no model/desktop).")] = False,
) -> None:
    """Start the hai-agent-runtime agent API on 127.0.0.1 and tail its log (Ctrl+C stops it)."""
    from rich.console import Console

    from holo_desktop.agent_client.sdk_runtime import SpawnConfig, ensure_local_runtime
    from holo_desktop.cli.bootstrap import load_holo_env, require_api_key

    load_holo_env()
    settings = load_holo_settings()
    if not fake:
        require_api_key(explicit_base_url=base_url, settings=settings)

    console = Console(stderr=True)
    try:
        runtime = ensure_local_runtime(
            SpawnConfig(port=port, model=model, base_url=base_url, fake=fake), settings=settings
        )
    except RuntimeError as exc:
        console.print(f"[bold red]✗[/bold red] {exc}")
        raise SystemExit(1) from exc

    console.print(
        f"[dim]agent API at {runtime.base_url} (pid {runtime.pid}, "
        f"v{runtime.version or 'unknown'}); log: {runtime.log_path}; Ctrl+C to stop.[/dim]"
    )
    try:
        if runtime.log_path is not None:
            _tail(runtime.log_path, console)
        else:
            # A spawned runtime always has a log path; this only fires on an oddly-shaped attach.
            console.print("[dim]no runtime log to tail; Ctrl+C to stop.[/dim]")
            while True:
                time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        if runtime.owned:
            runtime.shutdown()
    raise SystemExit(0)


def _tail(path: Path, console: Console) -> None:
    """Follow `path` forever, printing appended chunks (the foreground-stderr replacement)."""
    offset = 0
    while True:
        try:
            with path.open("r", encoding="utf-8", errors="replace") as fh:
                fh.seek(offset)
                chunk = fh.read()
                offset = fh.tell()
        except OSError:
            chunk = ""
        if chunk:
            console.out(chunk, end="")
        time.sleep(0.5)
