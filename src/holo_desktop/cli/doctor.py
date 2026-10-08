"""`holo doctor`: read-only environment diagnostics with one-line fix-its."""

from __future__ import annotations

from hai_agents_cli.doctor import CheckResult, check_desktop, check_runtime

from holo_desktop import customization
from holo_desktop.cli.bootstrap import key_source, load_holo_env
from holo_desktop.task import resolve_target


def check_login() -> CheckResult:
    try:
        base_url, model = resolve_target()
    except ValueError as exc:
        return CheckResult("login", False, "self-hosted server without a model", fix=str(exc))
    if base_url:
        return CheckResult("login", True, f"self-hosted model {model} at {base_url}")
    source = key_source()
    if source:
        return CheckResult("login", True, f"API key from {source}")
    return CheckResult("login", False, "no API key", fix="run `holo login`")


def check_skills() -> CheckResult:
    skills = sorted(customization.SKILLS_DIR.glob("*/SKILL.md"))
    if skills:
        return CheckResult("skills", True, f"{len(skills)} in {customization.SKILLS_DIR}")
    return CheckResult(
        "skills",
        False,
        f"none in {customization.SKILLS_DIR}",
        fix="bundled skills seed automatically on the first `holo run` / `holo mcp`",
    )


def run_checks() -> list[CheckResult]:
    return [check_runtime(), check_login(), check_skills(), check_desktop()]


def doctor() -> None:
    """Diagnose this machine's Holo setup: runtime, login, skills, desktop control. Read-only."""
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
