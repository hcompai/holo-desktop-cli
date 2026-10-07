"""`holo login` / `logout` / `whoami`: the SDK's browser sign-in and key store (`~/.config/hai/.env`)."""

from __future__ import annotations

import getpass
import platform
import sys
from typing import Annotated

import tyro
from dotenv import dotenv_values, unset_key
from hai_agents_common import credentials

from holo_desktop.cli import bootstrap

KEY_FALLBACK = f"Browser sign-in works with Google accounts. Otherwise create a key at {credentials.API_KEYS_PAGE} and run `holo login --key`."


def login(
    force: Annotated[bool, tyro.conf.arg(help="Sign in again and rotate this machine's key.")] = False,
    key: Annotated[
        bool, tyro.conf.arg(help=f"Store a key from {credentials.API_KEYS_PAGE} (hidden prompt, or stdin when piped).")
    ] = False,
) -> None:
    """Sign in to H Company. No-op if already signed in; pass --force to rotate the key."""
    from hai_agents_cli.auth import login_and_mint
    from rich.console import Console

    err = Console(stderr=True)
    bootstrap.load_holo_env()
    if credentials.current_api_key() and not force:
        err.print("[green]ok[/green] already signed in. Run [cyan]holo login --force[/cyan] to rotate the key.")
        return
    if key:
        pasted = (getpass.getpass("API key: ") if sys.stdin.isatty() else sys.stdin.readline()).strip()
        if not pasted:
            err.print("[red]x[/red] no key given.")
            raise SystemExit(1)
        err.print(f"[green]ok[/green] key saved to [cyan]{credentials.save_api_key(pasted)}[/cyan]")
        return

    host = platform.node().split(".", 1)[0] or "device"
    try:
        minted = login_and_mint(
            credentials.portal_base(),
            f"HoloDesktop CLI ({host})",
            lambda url: err.print(f"Opening your browser to sign in. If it does not open, visit:\n  {url}"),
        )
    except KeyboardInterrupt:
        err.print("\n[yellow]cancelled[/yellow].")
        raise SystemExit(130) from None
    except Exception as exc:
        err.print(f"[red]x[/red] sign-in failed: {exc}\n{KEY_FALLBACK}")
        raise SystemExit(1) from None
    err.print(f"[green]ok[/green] signed in; key saved to [cyan]{credentials.save_api_key(minted)}[/cyan]")


def logout() -> None:
    """Forget this machine's H Company API key."""
    if bootstrap.LEGACY_ENV_PATH.exists() and dotenv_values(bootstrap.LEGACY_ENV_PATH).get("HAI_API_KEY"):
        unset_key(str(bootstrap.LEGACY_ENV_PATH), "HAI_API_KEY")
    credentials.clear_api_key()
    print("signed out.", file=sys.stderr)


def whoami() -> None:
    """Print where the active API key comes from. Exits 1 if not signed in."""
    bootstrap.load_holo_env()
    source = bootstrap.key_source()
    if source is None:
        print("not signed in. Run `holo login`.", file=sys.stderr)
        raise SystemExit(1)
    print(f"signed in via {source}")
