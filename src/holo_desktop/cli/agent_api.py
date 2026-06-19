"""`holo agent-api`: launch the hai-agent-runtime binary in the foreground."""

from __future__ import annotations

import subprocess
from typing import Annotated

import tyro

from holo_desktop.agent_client.launcher import (
    AGENT_API_DEFAULT_PORT,
    AUTH_TOKEN_ENV,
    resolve_command,
    runtime_child_env,
)
from holo_desktop.settings import load_holo_settings


def agent_api(
    port: int = AGENT_API_DEFAULT_PORT,
    model: str | None = None,
    base_url: str | None = None,
    fake: Annotated[bool, tyro.conf.arg(help="Run the binary in fake-agent mode (no model/desktop).")] = False,
) -> None:
    """Start the hai-agent-runtime agent API on 127.0.0.1 (foreground)."""
    from rich.console import Console

    from holo_desktop.cli.bootstrap import load_holo_env, require_api_key

    load_holo_env()
    settings = load_holo_settings()
    if not fake:
        require_api_key(explicit_base_url=base_url, settings=settings)

    console = Console(stderr=True)
    extra = {"HAI_AGENT_RUNTIME_PORT": str(port)}
    if fake:
        extra["HAI_AGENT_RUNTIME_FAKE"] = "1"
    if model:
        extra["HAI_AGENT_RUNTIME_MODEL"] = model
    if base_url:
        extra["HAI_AGENT_RUNTIME_BASE_URL"] = base_url
    env = runtime_child_env(extra, settings=settings)

    try:
        cmd = resolve_command(settings=settings)
    except RuntimeError as exc:
        console.print(f"[bold red]✗[/bold red] {exc}")
        raise SystemExit(1) from exc

    if AUTH_TOKEN_ENV not in env:
        console.print(f"[dim]The binary will print an {AUTH_TOKEN_ENV} to export for clients.[/dim]")
    try:
        completed = subprocess.run(cmd, env=env, check=False)
    except KeyboardInterrupt:
        raise SystemExit(0) from None
    raise SystemExit(completed.returncode)
