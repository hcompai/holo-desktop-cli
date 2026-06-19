"""`holo doctor`: read-only environment diagnostics with one-line fix-its."""

from __future__ import annotations

import asyncio
import platform
import shutil

from pydantic import BaseModel

from holo_desktop import customization
from holo_desktop.agent_client import launcher, runtime_install
from holo_desktop.agent_client.launcher import (
    AUTH_TOKEN_ENV,
    LOOPBACK_HOST,
    log_tail_suggests_permissions,
    port_from_env,
    probe_health,
    token_file_path,
)
from holo_desktop.cli import bootstrap
from holo_desktop.cli.bootstrap import load_holo_env, read_user_env_key
from holo_desktop.cli.profile import load_profile
from holo_desktop.settings import HoloSettings, load_holo_settings

ACCESSIBILITY_SETTINGS_URL = "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
SCREEN_RECORDING_SETTINGS_URL = "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture"


class CheckResult(BaseModel):
    name: str
    ok: bool
    detail: str
    fix: str | None = None


def check_binary() -> CheckResult:
    on_path = shutil.which("hai-agent-runtime")
    if on_path:
        return CheckResult(name="binary", ok=True, detail=f"on PATH: {on_path}")
    managed = runtime_install.installed_binary(runtime_install.PINNED_RUNTIME_VERSION)
    if managed is not None:
        return CheckResult(
            name="binary", ok=True, detail=f"managed install (v{runtime_install.PINNED_RUNTIME_VERSION}): {managed}"
        )
    return CheckResult(
        name="binary",
        ok=False,
        detail="hai-agent-runtime not found (not on PATH, no managed install)",
        fix="any `holo run` downloads it automatically; or put hai-agent-runtime on PATH",
    )


def check_login(settings: HoloSettings) -> CheckResult:
    profile = load_profile()
    identity = f" · signed in as {profile.email} ({profile.org_name or profile.org_id})" if profile else ""
    if settings.auth.api_key:
        source = bootstrap.USER_ENV_PATH if read_user_env_key() else "process env"
        return CheckResult(name="login", ok=True, detail=f"HAI_API_KEY set ({source}){identity}")
    if settings.runtime.base_url:
        return CheckResult(
            name="login", ok=True, detail="self-hosted mode (HAI_AGENT_RUNTIME_BASE_URL set); no key needed"
        )
    return CheckResult(
        name="login",
        ok=False,
        detail="no HAI_API_KEY and no HAI_AGENT_RUNTIME_BASE_URL",
        fix="run `holo login`, or pass --base-url for a self-hosted model",
    )


def check_agent_api(settings: HoloSettings) -> CheckResult:
    port = port_from_env(settings=settings)
    probe = asyncio.run(probe_health(f"http://{LOOPBACK_HOST}:{port}"))
    if probe is None:
        return CheckResult(name="agent-api", ok=True, detail=f"no server on port {port} (spawns on demand)")
    version = probe.version or "unknown version"
    if version != runtime_install.PINNED_RUNTIME_VERSION and probe.version is not None:
        version = f"{version} (client pins {runtime_install.PINNED_RUNTIME_VERSION})"
    has_token = bool(settings.runtime.api_token) or token_file_path(port).is_file()
    if not has_token:
        return CheckResult(
            name="agent-api",
            ok=False,
            detail=f"server running on port {port} ({version}) but no credentials to attach",
            fix=f"export {AUTH_TOKEN_ENV}, or stop that server so holo can spawn its own",
        )
    return CheckResult(name="agent-api", ok=True, detail=f"server running on port {port} ({version}), token available")


def check_holo_dir() -> CheckResult:
    skills = sorted(customization.SKILLS_DIR.glob("*/SKILL.md"))
    logs = sorted(launcher.LOG_DIR.glob("hai-agent-runtime-*.log")) if launcher.LOG_DIR.is_dir() else []
    log_note = f"; latest runtime log: {logs[-1]}" if logs else ""
    if not skills:
        return CheckResult(
            name="holo-dir",
            ok=False,
            detail=f"no skills in {customization.SKILLS_DIR}{log_note}",
            fix="bundled skills seed automatically on the first `holo run` / `holo serve` / `holo mcp` / `holo acp`",
        )
    return CheckResult(name="holo-dir", ok=True, detail=f"{len(skills)} skill(s) seeded{log_note}")


def permissions_guidance_needed(port: int) -> bool:
    """macOS only: True when TCC grants are the likely culprit (heuristic; can't query another binary's grants)."""
    # platform.system() not sys.platform: mypy narrows the latter and flags this unreachable on Linux CI.
    if platform.system() != "Darwin":
        return False
    # A PATH binary (dev setup) never gets a first-run marker, so only the managed install counts as pending.
    managed_first_run_pending = shutil.which("hai-agent-runtime") is None and runtime_install.first_run_pending(
        runtime_install.PINNED_RUNTIME_VERSION
    )
    return managed_first_run_pending or log_tail_suggests_permissions(port)


def run_checks(settings: HoloSettings) -> list[CheckResult]:
    return [check_binary(), check_login(settings), check_agent_api(settings), check_holo_dir()]


def doctor() -> None:
    """Diagnose this machine's Holo setup: binary, login, agent API, ~/.holo. Read-only."""
    # Heavy imports are deferred into the command body to keep `holo --help` fast.
    from rich.console import Console
    from rich.panel import Panel

    load_holo_env()
    settings = load_holo_settings()
    out = Console()
    results = run_checks(settings)
    for result in results:
        mark = "[bold green]✓[/bold green]" if result.ok else "[bold red]✗[/bold red]"
        out.print(f"{mark} [bold]{result.name}[/bold] {result.detail}")
        if result.fix is not None:
            out.print(f"  [dim]fix:[/dim] {result.fix}")

    if permissions_guidance_needed(port_from_env(settings=settings)):
        out.print(
            Panel(
                "macOS cannot be queried for another app's grants, so verify manually that the runtime "
                "has [bold]Accessibility[/bold] and [bold]Screen Recording[/bold] under "
                "System Settings → Privacy & Security:\n"
                f"  • [link={ACCESSIBILITY_SETTINGS_URL}]Open Accessibility settings[/link]\n"
                f"  • [link={SCREEN_RECORDING_SETTINGS_URL}]Open Screen Recording settings[/link]\n"
                "After granting, the runtime must restart once for the grants to take effect.",
                title="[bold]macOS permissions[/bold]",
                title_align="left",
                border_style="dim",
                padding=(0, 2),
            )
        )

    if not all(result.ok for result in results):
        raise SystemExit(1)
