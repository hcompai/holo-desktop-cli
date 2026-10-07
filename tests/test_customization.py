"""User context from ~/.holo: agents.md, memories, rules and skills, plus per-OS bundled skill seeding."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from holo_desktop import customization


@pytest.fixture
def holo_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    home = tmp_path / ".holo"
    home.mkdir()
    monkeypatch.setattr(customization, "HOLO_DIR", home)
    monkeypatch.setattr(customization, "AGENTS_PATH", home / "agents.md")
    monkeypatch.setattr(customization, "MEMORIES_PATH", home / "memories.md")
    monkeypatch.setattr(customization, "HOLO_MEMORIES_PATH", home / "holo-memories.md")
    monkeypatch.setattr(customization, "RULES_PATH", home / "rules.md")
    monkeypatch.setattr(customization, "SKILLS_DIR", home / "skills")
    monkeypatch.setattr(customization, "SETTINGS_PATH", home / "settings.json")
    yield home


def _write_skill(home: Path, slug: str, frontmatter: str, body: str) -> None:
    skill_path = home / "skills" / slug / "SKILL.md"
    skill_path.parent.mkdir(parents=True, exist_ok=True)
    skill_path.write_text(f"---\n{frontmatter}\n---\n\n{body}\n", encoding="utf-8")


def test_valid_skills_load_under_a_deduped_kebab_slug(holo_home: Path) -> None:
    _write_skill(holo_home, "Apple_Calendar", "description: Calendar.\nname: Calendar", "Open Calendar.app.")
    _write_skill(holo_home, "apple-calendar", "description: Duplicate.", "Open Calendar.app.")
    _write_skill(holo_home, "no-description", "name: Broken", "Nothing here.")
    _write_skill(holo_home, "no-body", "description: Headless skill.", "")
    skills = customization.load_agent_context().skills
    assert [(s.name, s.body) for s in skills] == [("apple-calendar", "Open Calendar.app.")]


def test_instructions_fold_agents_md_memories_and_rules(holo_home: Path) -> None:
    (holo_home / "agents.md").write_text("---\nname: Kai\n---\n\nWrite in concise English.\n", encoding="utf-8")
    (holo_home / "memories.md").write_text("User prefers dark mode.\n\nUser lives in Berlin.\n", encoding="utf-8")
    (holo_home / "rules.md").write_text("Never delete files without confirming.\n", encoding="utf-8")
    rendered = customization.render_instructions(customization.load_agent_context())
    for fragment in (
        "You are talking to Kai.",
        "Write in concise English.",
        "## Memories",
        "- User lives in Berlin.",
        "## Rules",
        "- Never delete files without confirming.",
    ):
        assert fragment in rendered


def test_empty_sections_are_dropped(holo_home: Path) -> None:
    assert customization.render_instructions(customization.load_agent_context()) == ""
    (holo_home / "agents.md").write_text("Only agents.md is set.\n", encoding="utf-8")
    assert customization.render_instructions(customization.load_agent_context()) == "Only agents.md is set."


def test_malformed_frontmatter_keeps_the_users_text(holo_home: Path) -> None:
    (holo_home / "agents.md").write_text("---\nRemember: I prefer: terse replies\n---\n", encoding="utf-8")
    assert "terse replies" in customization.load_agent_context().agents_md


@pytest.mark.parametrize(
    ("system", "present", "absent", "chrome_hint"),
    [
        ("Darwin", {"apple-notes", "finder", "safari"}, {"file-explorer", "outlook"}, "Cmd+T"),
        ("Windows", {"file-explorer", "outlook", "edge"}, {"safari", "apple-notes"}, "Ctrl+T"),
    ],
)
def test_bundled_skills_seed_for_the_host_os(
    holo_home: Path, monkeypatch: pytest.MonkeyPatch, system: str, present: set, absent: set, chrome_hint: str
) -> None:
    monkeypatch.setattr(customization.platform, "system", lambda: system)
    customization.seed_bundled_skills()
    seeded = {p.parent.name for p in customization.SKILLS_DIR.glob("*/SKILL.md")}
    assert present <= seeded and absent.isdisjoint(seeded)
    assert chrome_hint in (customization.SKILLS_DIR / "chrome" / "SKILL.md").read_text(encoding="utf-8")


def test_unsupported_host_seeds_nothing(holo_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(customization.platform, "system", lambda: "Linux")
    customization.seed_bundled_skills()
    assert not list(customization.SKILLS_DIR.glob("*/SKILL.md"))
