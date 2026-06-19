"""On-disk identity bootstrap: layered .env loading + HAI_API_KEY persistence."""

import contextlib
import logging
import os
import sys

from dotenv import dotenv_values, load_dotenv, set_key

from holo_desktop.customization import HOLO_DIR, ensure_holo_dir, seed_bundled_skills
from holo_desktop.settings import HoloSettings, load_holo_settings

USER_ENV_PATH = HOLO_DIR / ".env"


def load_holo_env() -> None:
    """Layered dotenv: process env > `~/.holo/.env` > CWD `.env`."""
    if USER_ENV_PATH.exists():
        load_dotenv(USER_ENV_PATH)
    load_dotenv()


def read_user_env_key() -> str | None:
    """HAI_API_KEY stored in `~/.holo/.env`, or None. Does not touch the process env."""
    if not USER_ENV_PATH.exists():
        return None
    return dotenv_values(USER_ENV_PATH).get("HAI_API_KEY")


def save_hai_key(key: str) -> None:
    """Persist HAI_API_KEY to `~/.holo/.env` and the current process env."""
    ensure_holo_dir()
    if not USER_ENV_PATH.exists():
        os.close(os.open(USER_ENV_PATH, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600))
    # Tighten umask so set_key's write (and any temp-file rename) can't land the key world-readable.
    old_umask = os.umask(0o077)
    try:
        set_key(str(USER_ENV_PATH), "HAI_API_KEY", key)
    finally:
        os.umask(old_umask)
    with contextlib.suppress(OSError):
        os.chmod(USER_ENV_PATH, 0o600)
    os.environ["HAI_API_KEY"] = key


def require_api_key(*, explicit_base_url: str | None = None, settings: HoloSettings) -> None:
    """Ensure a HAI_API_KEY is set for Models API calls; auto-launch `holo login` on interactive TTYs."""
    if explicit_base_url or settings.auth.api_key:
        return

    from rich.console import Console

    err = Console(stderr=True)

    if sys.stdin.isatty() and sys.stdout.isatty():
        err.print()
        err.print("[dim]Signing in to H Company (one-time). Skip with --base-url for a local model.[/dim]")
        from holo_desktop.cli.login import login

        login()
        return

    err.print()
    err.print(
        "[bold red]No HAI_API_KEY found.[/bold red] Run [cyan]holo login[/cyan] to sign in with "
        f"your browser, or set [bold]HAI_API_KEY[/bold] (e.g. in {USER_ENV_PATH})."
    )
    err.print()
    sys.exit(1)


def require_api_key_stdio(*, settings: HoloSettings) -> None:
    """Non-interactive credential gate for stdio servers (mcp/acp), failing fast with a `holo login` pointer."""
    if settings.auth.api_key or settings.runtime.base_url or settings.runtime.fake:
        return
    print(
        "No HAI_API_KEY found. Run `holo login` in a terminal to sign in with your browser, "
        f"or set HAI_API_KEY (e.g. in {USER_ENV_PATH}).",
        file=sys.stderr,
    )
    sys.exit(1)


def configure_stdio_logging(logger_name: str) -> None:
    """Stderr WARNING+ logging shared by stdio servers (`holo mcp`, `holo acp`)."""
    logging.basicConfig(
        level=logging.WARNING,
        stream=sys.stderr,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger(logger_name).setLevel(logging.WARNING)


def bootstrap_interactive(*, base_url: str | None, fake: bool) -> HoloSettings:
    """Shared startup for the interactive surfaces (`holo run`, `holo serve`)."""
    load_holo_env()
    settings = load_holo_settings()
    if not fake:
        require_api_key(explicit_base_url=base_url, settings=settings)
    seed_bundled_skills()
    return settings


def ensure_guard_running() -> None:
    """Best-effort: nudge an already-installed kill-switch guard to load (headless surfaces).

    Headless surfaces (`holo mcp` under a host, `holo serve`, `holo acp`) have no interactive process
    to host a listener, so the OS-launched guard is what makes the double-Esc stop reachable. The guard
    is installed by `holo install`; here we only load it if present, never install it behind the scenes.
    """
    try:
        from holo_desktop.killswitch.autostart import ensure_loaded

        ensure_loaded()
    except Exception:
        logging.getLogger(__name__).debug("kill-switch guard load skipped", exc_info=True)


def install_sigterm_graceful() -> None:
    """Map SIGTERM to KeyboardInterrupt so a host killing the stdio server still runs async teardown."""
    import signal

    with contextlib.suppress(ValueError, OSError):
        signal.signal(signal.SIGTERM, signal.default_int_handler)


def bootstrap_stdio(logger_name: str) -> HoloSettings:
    """Shared startup for the stdio servers (`holo mcp`, `holo acp`)."""
    configure_stdio_logging(logger_name)
    install_sigterm_graceful()
    load_holo_env()
    settings = load_holo_settings()
    seed_bundled_skills()
    require_api_key_stdio(settings=settings)
    ensure_guard_running()
    return settings
