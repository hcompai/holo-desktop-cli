"""Private installer bootstrap used by install.sh and install.ps1."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from hai_agents_local.runtime import LocalRuntimeError
from hai_agents_local.runtime.install import install_runtime, installed_binary, pinned_artifact
from hai_agents_local.runtime.manifest import PINNED_RUNTIME_VERSION
from rich.console import Console

from holo_desktop.customization import seed_bundled_skills


def find_runtime() -> Path | None:
    """The runtime the SDK will launch: `hai-agent-runtime` on PATH, else the managed install."""
    on_path = shutil.which("hai-agent-runtime")
    return Path(on_path) if on_path else installed_binary(PINNED_RUNTIME_VERSION)


def bootstrap_installer(*, login: bool = False, install_hosts: bool = False) -> None:
    """Download local Holo assets and print the next commands to run."""
    err = Console(stderr=True)
    seed_bundled_skills()
    try:
        runtime_path = find_runtime() or install_runtime(pinned_artifact(), version=PINNED_RUNTIME_VERSION)
    except LocalRuntimeError as exc:
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Private Holo installer bootstrap.")
    parser.add_argument("--login", action="store_true", help="Open browser sign-in after installing local assets.")
    parser.add_argument(
        "--install-hosts", action="store_true", help="Wire detected agent hosts after installing local assets."
    )
    args = parser.parse_args()
    bootstrap_installer(login=args.login, install_hosts=args.install_hosts)


if __name__ == "__main__":
    main()
