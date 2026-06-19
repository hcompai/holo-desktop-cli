"""`holo whoami`: print the cached identity. Offline; reads `~/.holo/profile.json`."""

import sys

from holo_desktop.cli.bootstrap import USER_ENV_PATH, load_holo_env, read_user_env_key
from holo_desktop.cli.profile import load_profile
from holo_desktop.settings import load_holo_settings


def whoami() -> None:
    """Print signed-in identity (email, org, key label). Exits 1 if not signed in."""
    from rich.console import Console

    out = Console()
    err = Console(stderr=True)

    load_holo_env()
    active_key = load_holo_settings().auth.api_key
    if not active_key:
        err.print("[yellow]not signed in.[/yellow] Run [cyan]holo login[/cyan].")
        sys.exit(1)

    # Cache only describes keys written by `holo login`; hide it if HAI_API_KEY came from elsewhere.
    cache_valid = read_user_env_key() == active_key
    profile = load_profile() if cache_valid else None

    if profile is None:
        if cache_valid:
            out.print(
                f"signed in via [bold]{USER_ENV_PATH}[/bold]; run [cyan]holo login[/cyan] to cache your identity."
            )
        else:
            out.print(
                "signed in via [bold]HAI_API_KEY[/bold] env override; "
                "run [cyan]holo login[/cyan] to switch to a managed key."
            )
        return

    org = profile.org_name or profile.org_id
    out.print(f"[bold]{profile.email}[/bold] / org [bold]{org}[/bold]")
    out.print(f"  key: {profile.key_label}")
