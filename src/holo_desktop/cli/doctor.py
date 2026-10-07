"""`holo doctor`: read-only environment diagnostics with one-line fix-its."""

from __future__ import annotations

import platform

from hai_agents_local.desktop import ACCESSIBILITY_SETTINGS_URL, SCREEN_RECORDING_SETTINGS_URL
from pydantic import BaseModel

from holo_desktop import customization
from holo_desktop.cli.bootstrap import key_source, load_holo_env
from holo_desktop.installer_bootstrap import find_runtime
from holo_desktop.task import resolve_target


class CheckResult(BaseModel):
    name: str
    ok: bool
    detail: str
    fix: str | None = None


def check_runtime() -> CheckResult:
    path = find_runtime()
    if path is not None:
        return CheckResult(name="runtime", ok=True, detail=str(path))
    return CheckResult(
        name="runtime", ok=True, detail="not installed yet", fix="the first `holo run` downloads it automatically"
    )


def check_login() -> CheckResult:
    base_url, model = resolve_target()
    if base_url:
        return CheckResult(name="login", ok=True, detail=f"self-hosted model {model or '(unset)'} at {base_url}")
    source = key_source()
    if source:
        return CheckResult(name="login", ok=True, detail=f"API key from {source}")
    return CheckResult(name="login", ok=False, detail="no API key", fix="run `holo login`")


def check_skills() -> CheckResult:
    skills = sorted(customization.SKILLS_DIR.glob("*/SKILL.md"))
    if skills:
        return CheckResult(name="skills", ok=True, detail=f"{len(skills)} in {customization.SKILLS_DIR}")
    return CheckResult(
        name="skills",
        ok=False,
        detail=f"none in {customization.SKILLS_DIR}",
        fix="bundled skills seed automatically on the first `holo run` / `holo mcp`",
    )


def check_macos_grants() -> CheckResult | None:
    """This process's Accessibility and Screen Recording grants; non-prompting, so the doctor stays read-only."""
    # platform.system() not sys.platform: mypy narrows the latter and flags this unreachable on Linux CI.
    if platform.system() != "Darwin":
        return None
    from ApplicationServices import AXIsProcessTrusted
    from Quartz import CGPreflightScreenCaptureAccess

    missing = [
        name
        for name, granted in (
            ("Accessibility", AXIsProcessTrusted()),
            ("Screen Recording", CGPreflightScreenCaptureAccess()),
        )
        if not granted
    ]
    if not missing:
        return CheckResult(name="macos", ok=True, detail="Accessibility and Screen Recording granted")
    return CheckResult(
        name="macos",
        ok=False,
        detail=f"this terminal lacks {' and '.join(missing)}",
        fix=f"grant the app that runs Holo, then restart it: {ACCESSIBILITY_SETTINGS_URL} , {SCREEN_RECORDING_SETTINGS_URL}",
    )


def run_checks() -> list[CheckResult]:
    checks = [check_runtime(), check_login(), check_skills(), check_macos_grants()]
    return [check for check in checks if check is not None]


def doctor() -> None:
    """Diagnose this machine's Holo setup: runtime, login, skills, macOS grants. Read-only."""
    from rich.console import Console

    load_holo_env()
    out = Console()
    results = run_checks()
    for result in results:
        mark = "[bold green]✓[/bold green]" if result.ok else "[bold red]✗[/bold red]"
        out.print(f"{mark} [bold]{result.name}[/bold] {result.detail}")
        if result.fix is not None:
            out.print(f"  [dim]fix:[/dim] {result.fix}")
    if not all(result.ok for result in results):
        raise SystemExit(1)
