"""Process startup shared by `holo run` and `holo mcp`: env loading, sign-in gate, stdio hygiene."""

import contextlib
import logging
import signal
import sys

from dotenv import dotenv_values, load_dotenv
from hai_agents_common import credentials
from hai_agents_common.credentials import current_api_key

from holo_desktop.customization import HOLO_DIR, seed_bundled_skills

LEGACY_ENV_PATH = HOLO_DIR / ".env"
NO_KEY_MESSAGE = "No H Company API key found. Run `holo login` in a terminal, or set HAI_API_KEY."


def load_holo_env() -> None:
    """Layered dotenv: process env > `~/.holo/.env` > CWD `.env`; the SDK then falls back to `~/.config/hai/.env`."""
    if LEGACY_ENV_PATH.exists():
        load_dotenv(LEGACY_ENV_PATH)
    load_dotenv()


def key_source() -> str | None:
    """Where the active API key comes from: `environment`, or the file that holds it."""
    source = credentials.source()
    legacy = dotenv_values(LEGACY_ENV_PATH).get("HAI_API_KEY") if LEGACY_ENV_PATH.exists() else None
    if source == "environment" and legacy and legacy == current_api_key():
        return str(LEGACY_ENV_PATH)
    return source


def bootstrap_interactive(*, base_url: str | None, model: str | None) -> tuple[str | None, str | None]:
    """Startup for `holo run`: env, skills, a one-time browser sign-in on a TTY; returns the self-hosted target."""
    from holo_desktop.task import resolve_target

    load_holo_env()
    seed_bundled_skills()
    base_url, model = resolve_target(base_url, model)
    if base_url or current_api_key():
        return base_url, model
    if sys.stdin.isatty() and sys.stdout.isatty():
        from holo_desktop.cli.login import login

        login()
        return base_url, model
    print(NO_KEY_MESSAGE, file=sys.stderr)
    raise SystemExit(1)


def ensure_guard_running() -> None:
    """Best-effort: load an installed kill-switch guard, the only double-Esc listener under a headless host."""
    try:
        from holo_desktop.killswitch.autostart import ensure_loaded

        ensure_loaded()
    except Exception:
        logging.getLogger(__name__).debug("kill-switch guard load skipped", exc_info=True)


def bootstrap_stdio() -> None:
    """Startup for the `holo mcp` stdio server: SIGTERM teardown, sign-in gate, guard."""
    from holo_desktop.task import resolve_target

    # A host killing the server sends SIGTERM; raising KeyboardInterrupt still runs async teardown.
    with contextlib.suppress(ValueError, OSError):
        signal.signal(signal.SIGTERM, signal.default_int_handler)
    load_holo_env()
    seed_bundled_skills()
    try:
        base_url, _ = resolve_target()
    except ValueError as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(1) from None
    if not (base_url or current_api_key()):
        print(NO_KEY_MESSAGE, file=sys.stderr)
        raise SystemExit(1)
    ensure_guard_running()
