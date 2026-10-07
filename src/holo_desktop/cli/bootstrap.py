"""Process startup shared by `holo run` and `holo mcp`: env loading, sign-in gate, stdio hygiene."""

import contextlib
import logging
import signal
import sys

from dotenv import load_dotenv
from hai_agents_common.credentials import current_api_key

from holo_desktop.customization import HOLO_DIR, seed_bundled_skills

LEGACY_ENV_PATH = HOLO_DIR / ".env"
NO_KEY_MESSAGE = "No H Company API key found. Run `holo login` in a terminal, or set HAI_API_KEY."


def load_holo_env() -> None:
    """Layered dotenv: process env > `~/.holo/.env` > CWD `.env`; the SDK then falls back to `~/.config/hai/.env`."""
    if LEGACY_ENV_PATH.exists():
        load_dotenv(LEGACY_ENV_PATH)
    load_dotenv()


def bootstrap_interactive(*, base_url: str | None) -> None:
    """Startup for `holo run`: env, skills, and a one-time browser sign-in on a TTY."""
    load_holo_env()
    seed_bundled_skills()
    if base_url or current_api_key():
        return
    if sys.stdin.isatty() and sys.stdout.isatty():
        from holo_desktop.cli.login import login

        login()
        return
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
    """Startup for the `holo mcp` stdio server: stderr-only logs, SIGTERM teardown, sign-in gate, guard."""
    from holo_desktop.task import resolve_target

    logging.basicConfig(
        level=logging.WARNING, stream=sys.stderr, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    # A host killing the server sends SIGTERM; raising KeyboardInterrupt still runs async teardown.
    with contextlib.suppress(ValueError, OSError):
        signal.signal(signal.SIGTERM, signal.default_int_handler)
    load_holo_env()
    seed_bundled_skills()
    base_url, _ = resolve_target()
    if not (base_url or current_api_key()):
        print(NO_KEY_MESSAGE, file=sys.stderr)
        raise SystemExit(1)
    ensure_guard_running()
