"""`holo setup`: finish local machine setup after installer bootstrap."""

from __future__ import annotations

from typing import Annotated

import tyro
from rich.console import Console

from holo_desktop.agent_client.runtime_install import RuntimeArtifactUnavailable, ensure_managed_runtime
from holo_desktop.cli.bootstrap import load_holo_env
from holo_desktop.customization import seed_bundled_skills
from holo_desktop.settings import load_holo_settings


def setup(
    yes: Annotated[bool, tyro.conf.arg(help="Download the managed runtime without prompting.")] = False,
    login: Annotated[bool, tyro.conf.arg(help="Open browser sign-in after installing local assets.")] = False,
    install_hosts: Annotated[
        bool, tyro.conf.arg(help="Wire detected agent hosts after installing local assets.")
    ] = False,
) -> None:
    """Download local Holo assets and print the next commands to run."""
    err = Console(stderr=True)
    load_holo_env()
    settings = load_holo_settings()
    seed_bundled_skills()
    try:
        runtime_path = ensure_managed_runtime(settings=settings.install, assume_yes=yes)
    except RuntimeArtifactUnavailable as exc:
        err.print(f"[bold red]x[/bold red] {exc}")
        raise SystemExit(1) from exc
    err.print(f"[green]ok[/green] runtime ready: [cyan]{runtime_path}[/cyan]")

    if login:
        from holo_desktop.cli.login import login as run_login

        run_login()
    else:
        err.print("Next: [cyan]holo login[/cyan]")

    if install_hosts:
        from holo_desktop.cli.install import install

        install()
    else:
        err.print("Optional: [cyan]holo install[/cyan] to wire supported agent hosts.")
