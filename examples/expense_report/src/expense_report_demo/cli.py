"""`expense-report-demo` CLI. tyro subcommands: list, run, install-skills, pin-fixtures."""

from __future__ import annotations

import contextlib
import io
import sys
from importlib import resources
from pathlib import Path
from typing import Annotated

import tyro
from holo_desktop.agent_client.launcher import port_from_env
from holo_desktop.cli.bootstrap import load_holo_env
from holo_desktop.settings import load_holo_settings

from expense_report_demo import fixtures as fixtures_mod
from expense_report_demo.demos import registry
from expense_report_demo.demos.runner import run_demo
from expense_report_demo.holo_kwargs import HoloKwargs

DEFAULT_DEMO_RUNS_DIR = Path("runs")
DEFAULT_FIXTURES_CACHE_DIR = Path("fixtures") / ".cache"
BUNDLED_SKILLS_PACKAGE = "expense_report_demo.skills"

# Process exit code per demo outcome; 130 is the conventional code for SIGINT (Ctrl-C).
_EXIT_CODES: dict[str, int] = {"ok": 0, "error": 1, "interrupted": 130}


# --------------------------------------------------------------------------- #
#                                    list                                     #
# --------------------------------------------------------------------------- #


def list_all() -> None:
    """Print available demos and installed skills."""
    print("demos:")
    for slug, demo in sorted(registry.REGISTRY.items()):
        print(f"  {slug:24} {demo.title}")
    skills_dir = Path.home() / ".holo" / "skills"
    print("\ninstalled skills (~/.holo/skills/):")
    if not skills_dir.is_dir():
        print("  (none — run `expense-report-demo install-skills`)")
        return
    for entry in sorted(skills_dir.iterdir()):
        if entry.is_dir() and (entry / "SKILL.md").is_file():
            print(f"  {entry.name}")


# --------------------------------------------------------------------------- #
#                                     run                                     #
# --------------------------------------------------------------------------- #


def run(
    slug: Annotated[str, tyro.conf.Positional, tyro.conf.arg(metavar="SLUG")],
    *,
    out: Path = DEFAULT_DEMO_RUNS_DIR,
    dry_run: bool = False,
    model: str | None = None,
    base_url: str | None = None,
    max_steps: int | None = None,
    max_time_s: float | None = None,
    port: int | None = None,
    fake: bool = False,
    expand: bool = False,
    profile: bool = False,
) -> None:
    """Run one demo by slug. `--dry-run` plans without starting a session. `--expand` prints every step as a full panel. `--profile` prints a per-step observe/llm/tool timing table."""
    demo = registry.get(slug)
    load_holo_env()
    settings = load_holo_settings()
    kwargs = HoloKwargs(
        max_steps=max_steps if max_steps is not None else demo.max_steps,
        max_time_s=max_time_s if max_time_s is not None else demo.max_time_s,
        model=model,
        llm_base_url=base_url,
        port=port if port is not None else port_from_env(settings=settings),
        fake=fake,
    )
    result = run_demo(
        demo,
        kwargs,
        out,
        dry_run=dry_run,
        hooks=registry.get_hooks(slug),
        verifier=registry.get_verifier(slug),
        expand_feed=expand,
        profile=profile,
    )
    # Non-zero exit so scripts/CI can detect a failed run; success returns normally.
    code = _EXIT_CODES[result.outcome]
    if code != 0:
        raise SystemExit(code)


# --------------------------------------------------------------------------- #
#                              install-skills                                 #
# --------------------------------------------------------------------------- #


def install_skills(*, force: bool = False) -> None:
    """Copy bundled `src/expense_report_demo/skills/<slug>/SKILL.md` into `~/.holo/skills/`.

    Idempotent: skips entries that already exist unless `--force` is set."""
    dest_root = Path.home() / ".holo" / "skills"
    dest_root.mkdir(parents=True, exist_ok=True)
    pkg = resources.files(BUNDLED_SKILLS_PACKAGE)
    copied: list[str] = []
    skipped: list[str] = []
    for entry in sorted(pkg.iterdir(), key=lambda e: e.name):
        slug = entry.name
        if not entry.is_dir() or slug.startswith(("_", ".")):
            continue
        src_file = entry / "SKILL.md"
        try:
            text = src_file.read_text(encoding="utf-8")
        except (FileNotFoundError, OSError):
            continue
        dest_file = dest_root / slug / "SKILL.md"
        if dest_file.exists() and not force:
            existing = dest_file.read_text(encoding="utf-8")
            if existing == text:
                skipped.append(slug)
                continue
            print(
                f"  [skills] WARN: {dest_file} differs from bundled; pass --force to overwrite",
                file=sys.stderr,
            )
            skipped.append(slug)
            continue
        dest_file.parent.mkdir(parents=True, exist_ok=True)
        dest_file.write_text(text, encoding="utf-8")
        copied.append(slug)
    print(f"  [skills] copied {len(copied)}: {copied}")
    if skipped:
        print(f"  [skills] skipped {len(skipped)}: {skipped}")


# --------------------------------------------------------------------------- #
#                              pin-fixtures                                   #
# --------------------------------------------------------------------------- #


def pin_fixtures(
    manifest: Annotated[Path, tyro.conf.Positional, tyro.conf.arg(metavar="MANIFEST")],
    *,
    dest_root: Path | None = None,
) -> None:
    """Compute missing sha256s, write them back into `manifest`, and download every entry into its dest."""
    if not manifest.is_file():
        print(f"manifest not found: {manifest}", file=sys.stderr)
        raise SystemExit(2)
    slug = manifest.stem
    target = dest_root or Path("fixtures") / slug
    fixtures_mod.pin(manifest, target, cache_dir=DEFAULT_FIXTURES_CACHE_DIR)


# --------------------------------------------------------------------------- #
#                                     main                                    #
# --------------------------------------------------------------------------- #


def main() -> None:
    """Entrypoint for `expense-report-demo`."""
    # Force UTF-8 stdio so rich glyphs survive non-UTF locales.
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            with contextlib.suppress(OSError, ValueError):
                stream.reconfigure(encoding="utf-8", errors="replace")
    tyro.extras.subcommand_cli_from_dict(
        {
            "list": list_all,
            "run": run,
            "install-skills": install_skills,
            "pin-fixtures": pin_fixtures,
        }
    )


__all__ = ["main"]
