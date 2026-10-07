"""`holo doctor`: read-only environment diagnostics with one-line fix-its."""

from __future__ import annotations

import platform
import shutil

from hai_agents_local.desktop import ACCESSIBILITY_SETTINGS_URL, SCREEN_RECORDING_SETTINGS_URL
from hai_agents_local.runtime import LocalRuntime, LocalRuntimeError
from pydantic import BaseModel

from holo_desktop import customization
from holo_desktop.agent_client import runtime_install
from holo_desktop.agent_client.launcher import (
    log_tail_suggests_permissions,
    port_from_env,
    runtime_log_path,
)
from holo_desktop.cli import bootstrap
from holo_desktop.cli.bootstrap import load_holo_env, read_user_env_key
from holo_desktop.cli.profile import load_profile
from holo_desktop.settings import AUTH_TOKEN_ENV, HoloSettings, load_holo_settings


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
    try:
        runtime = LocalRuntime.attach(port=port)
    except LocalRuntimeError as exc:
        return CheckResult(
            name="agent-api",
            ok=False,
            detail=f"server on port {port} cannot be attached: {exc}",
            fix=f"export {AUTH_TOKEN_ENV}, or stop that server so holo can spawn its own",
        )
    if runtime is None:
        return CheckResult(name="agent-api", ok=True, detail=f"no server on port {port} (spawns on demand)")
    version = runtime.version or "unknown version"
    if runtime.version is not None and runtime.version != runtime_install.PINNED_RUNTIME_VERSION:
        version = f"{version} (client pins {runtime_install.PINNED_RUNTIME_VERSION})"
    return CheckResult(name="agent-api", ok=True, detail=f"server running on port {port} ({version}), token verified")


def check_holo_dir(settings: HoloSettings) -> CheckResult:
    skills = sorted(customization.SKILLS_DIR.glob("*/SKILL.md"))
    log_dir = runtime_log_path(port_from_env(settings=settings)).parent
    logs = sorted(log_dir.glob("hai-agent-runtime-*.log")) if log_dir.is_dir() else []
    log_note = f"; latest runtime log: {logs[-1]}" if logs else ""
    if not skills:
        return CheckResult(
            name="holo-dir",
            ok=False,
            detail=f"no skills in {customization.SKILLS_DIR}{log_note}",
            fix="bundled skills seed automatically on the first `holo run` / `holo mcp`",
        )
    return CheckResult(name="holo-dir", ok=True, detail=f"{len(skills)} skill(s) seeded{log_note}")


def missing_macos_grants() -> list[str]:
    """macOS grants this process lacks; non-prompting, so the doctor stays read-only."""
    from ApplicationServices import AXIsProcessTrusted
    from Quartz import CGPreflightScreenCaptureAccess

    missing = []
    if not AXIsProcessTrusted():
        missing.append("Accessibility")
    if not CGPreflightScreenCaptureAccess():
        missing.append("Screen Recording")
    return missing


def permissions_guidance(port: int) -> str | None:
    """macOS grants to fix, or None: this process's own, plus the runtime's when its log shows a denial."""
    # platform.system() not sys.platform: mypy narrows the latter and flags this unreachable on Linux CI.
    if platform.system() != "Darwin":
        return None
    lines = []
    missing = missing_macos_grants()
    if missing:
        lines.append(
            f"This terminal lacks [bold]{' and '.join(missing)}[/bold]. Holo drives the desktop from the app "
            "that runs it (this terminal, or your MCP host): grant that app, then restart it."
        )
    if log_tail_suggests_permissions(port):
        lines.append(
            "The runtime log shows a permission denial from a [cyan]--fast[/cyan] run, which drives the "
            "desktop from the runtime: grant the runtime too, then restart it."
        )
    return "\n".join(lines) or None


def run_checks(settings: HoloSettings) -> list[CheckResult]:
    return [check_binary(), check_login(settings), check_agent_api(settings), check_holo_dir(settings)]


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

    guidance = permissions_guidance(port_from_env(settings=settings))
    if guidance is not None:
        out.print(
            Panel(
                f"{guidance}\nGrant under System Settings → Privacy & Security:\n"
                f"  • [link={ACCESSIBILITY_SETTINGS_URL}]Open Accessibility settings[/link]\n"
                f"  • [link={SCREEN_RECORDING_SETTINGS_URL}]Open Screen Recording settings[/link]",
                title="[bold]macOS permissions[/bold]",
                title_align="left",
                border_style="dim",
                padding=(0, 2),
            )
        )

    if not all(result.ok for result in results):
        raise SystemExit(1)
