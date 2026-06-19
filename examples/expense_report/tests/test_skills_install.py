"""Behavioural test for `expense-report-demo install-skills`. Uses `fake_home` as $HOME so we
don't touch the user's real ~/.holo/skills/."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from expense_report_demo import cli

_EXPECTED_SKILLS = {"expense-report"}


def test_install_skills_copies_bundled_skills(fake_home: Path) -> None:
    cli.install_skills(force=False)

    skills_dir = fake_home / ".holo" / "skills"
    actual = {p.name for p in skills_dir.iterdir() if p.is_dir()}
    assert _EXPECTED_SKILLS.issubset(actual), f"missing skills: {_EXPECTED_SKILLS - actual}"

    for slug in _EXPECTED_SKILLS:
        skill_md = skills_dir / slug / "SKILL.md"
        assert skill_md.is_file(), f"{skill_md} not written"
        content = skill_md.read_text(encoding="utf-8")
        assert content.startswith("---"), "expected YAML frontmatter at top of SKILL.md"
        assert "name:" in content
        assert "description:" in content


def test_install_skills_is_idempotent(fake_home: Path) -> None:
    cli.install_skills(force=False)
    skill_md = fake_home / ".holo" / "skills" / "expense-report" / "SKILL.md"
    first_mtime = skill_md.stat().st_mtime

    # Second call should not rewrite identical files.
    time.sleep(0.05)
    cli.install_skills(force=False)
    assert skill_md.stat().st_mtime == first_mtime, "idempotent run should not modify on-disk file"


def test_install_skills_force_rewrites_modified_files(fake_home: Path) -> None:
    cli.install_skills(force=False)
    skill_md = fake_home / ".holo" / "skills" / "expense-report" / "SKILL.md"
    original = skill_md.read_text(encoding="utf-8")

    # User-modified version.
    skill_md.write_text("---\nname: Local\ndescription: local override\n---\nhand-edited\n")
    cli.install_skills(force=True)
    assert skill_md.read_text(encoding="utf-8") == original


def test_install_skills_warns_on_local_drift_without_force(fake_home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    cli.install_skills(force=False)
    skill_md = fake_home / ".holo" / "skills" / "expense-report" / "SKILL.md"
    drift = "---\nname: Local\ndescription: drift\n---\n"
    skill_md.write_text(drift)

    cli.install_skills(force=False)
    out = capsys.readouterr()
    assert "differs from bundled" in out.err or "differs from bundled" in out.out
    assert skill_md.read_text(encoding="utf-8") == drift, "without --force, drift must not be overwritten"
