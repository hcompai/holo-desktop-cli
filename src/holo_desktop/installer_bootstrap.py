"""Private installer bootstrap used by install.sh and install.ps1."""

from __future__ import annotations

import argparse

from hai_agents.local import LocalRuntime, LocalRuntimeError
from rich.console import Console
from rich.prompt import Confirm

from holo_desktop.agent_client.sdk_runtime import SpawnConfig, ensure_local_runtime
from holo_desktop.cli.bootstrap import load_holo_env
from holo_desktop.customization import seed_bundled_skills
from holo_desktop.settings import HoloSettings, load_holo_settings


def _runtime_for_installer(*, settings: HoloSettings, assume_yes: bool) -> LocalRuntime:
    """Attach to or start the SDK-managed runtime used by the installed CLI."""
    existing = LocalRuntime.attach(port=settings.runtime.port)
    if existing is not None:
        return existing
    if not assume_yes and not Confirm.ask("Download and start hai-agent-runtime?", default=True):
        raise LocalRuntimeError("hai-agent-runtime download declined")
    return ensure_local_runtime(
        SpawnConfig(port=settings.runtime.port, require_fresh_for_config=False),
        settings=settings,
    )


def bootstrap_installer(*, yes: bool = False, login: bool = False, install_hosts: bool = False) -> None:
    """Download local Holo assets and print the next commands to run."""
    err = Console(stderr=True)
    load_holo_env()
    settings = load_holo_settings()
    seed_bundled_skills()
    try:
        runtime = _runtime_for_installer(settings=settings, assume_yes=yes)
    except LocalRuntimeError as exc:
        err.print(f"[bold red]x[/bold red] {exc}")
        raise SystemExit(1) from exc
    err.print(f"[green]ok[/green] runtime ready: [cyan]{runtime.base_url}[/cyan]")

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


def main() -> None:
    parser = argparse.ArgumentParser(description="Private Holo installer bootstrap.")
    parser.add_argument("--yes", action="store_true", help="Download the managed runtime without prompting.")
    parser.add_argument("--login", action="store_true", help="Open browser sign-in after installing local assets.")
    parser.add_argument(
        "--install-hosts", action="store_true", help="Wire detected agent hosts after installing local assets."
    )
    args = parser.parse_args()
    bootstrap_installer(yes=args.yes, login=args.login, install_hosts=args.install_hosts)


if __name__ == "__main__":
    main()
