"""Behavioural tests for ``holo_desktop.customization``.

We patch ``HOLO_DIR`` (and every derived path constant) to a tmp dir per test
so we don't read or scribble on the developer's real ``~/.holo/``.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from agent_interface.specs.skill import Skill

from holo_desktop import customization


@pytest.fixture
def holo_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Re-point every customization module-level path constant at ``tmp_path``.

    The module pre-computes ``AGENTS_PATH`` etc. at import time, so mutating
    ``HOLO_DIR`` alone is not enough.
    """
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


def _write_skill(home: Path, slug: str, frontmatter: str, body: str) -> Path:
    """Drop a skill at ``<home>/skills/<slug>/SKILL.md`` and return the path."""
    skill_path = home / "skills" / slug / "SKILL.md"
    skill_path.parent.mkdir(parents=True, exist_ok=True)
    skill_path.write_text(f"---\n{frontmatter}\n---\n\n{body}\n", encoding="utf-8")
    return skill_path


def test_load_agent_context_returns_skills(holo_home: Path) -> None:
    _write_skill(
        holo_home,
        slug="safari",
        frontmatter="description: Drive the Safari browser.\nname: Safari\npublisher: H Company\nbundle_id: com.apple.Safari",
        body="Open Safari with Cmd+Space.",
    )

    ctx = customization.load_agent_context()

    assert len(ctx.skills) == 1
    skill = ctx.skills[0]
    assert isinstance(skill, Skill)
    assert skill.name == "safari"  # slug wins; display "Safari" is dropped
    assert skill.description == "Drive the Safari browser."
    assert skill.body == "Open Safari with Cmd+Space."


def test_load_agent_context_skips_skills_with_no_description(holo_home: Path) -> None:
    _write_skill(holo_home, "broken", frontmatter="name: Broken", body="Nothing here.")
    ctx = customization.load_agent_context()
    assert ctx.skills == ()


def test_load_agent_context_skips_skills_with_no_body(holo_home: Path) -> None:
    _write_skill(holo_home, "headless", frontmatter="description: Headless skill.", body="")
    ctx = customization.load_agent_context()
    assert ctx.skills == ()


def test_load_agent_context_coerces_slug_to_kebab(holo_home: Path) -> None:
    _write_skill(holo_home, "Apple_Calendar", frontmatter="description: Calendar.", body="Open Calendar.app.")
    ctx = customization.load_agent_context()
    assert len(ctx.skills) == 1
    assert ctx.skills[0].name == "apple-calendar"


def test_render_instructions_folds_agents_md_memories_rules(holo_home: Path) -> None:
    (holo_home / "agents.md").write_text("---\nname: Kai\n---\n\nWrite in concise English.\n", encoding="utf-8")
    (holo_home / "memories.md").write_text("User prefers dark mode.\n\nUser lives in Berlin.\n", encoding="utf-8")
    (holo_home / "rules.md").write_text("Never delete files without confirming.\n", encoding="utf-8")

    ctx = customization.load_agent_context()
    rendered = customization.render_instructions(ctx)

    assert "You are talking to Kai." in rendered
    assert "Write in concise English." in rendered
    assert "## Memories" in rendered
    assert "- User prefers dark mode." in rendered
    assert "- User lives in Berlin." in rendered
    assert "## Rules" in rendered
    assert "- Never delete files without confirming." in rendered


def test_render_instructions_drops_empty_sections(holo_home: Path) -> None:
    (holo_home / "agents.md").write_text("Only agents.md is set.\n", encoding="utf-8")
    ctx = customization.load_agent_context()
    rendered = customization.render_instructions(ctx)
    assert rendered == "Only agents.md is set."
    assert "## Memories" not in rendered
    assert "## Rules" not in rendered


def test_render_instructions_empty_context_renders_empty_string(holo_home: Path) -> None:
    ctx = customization.load_agent_context()
    assert customization.render_instructions(ctx) == ""


def test_agents_md_with_malformed_frontmatter_and_empty_body_is_not_dropped(holo_home: Path) -> None:
    """A frontmatter fence whose YAML is invalid (and nothing after it) must keep the user's text."""
    (holo_home / "agents.md").write_text("---\nRemember: I prefer: terse replies\n---\n", encoding="utf-8")
    ctx = customization.load_agent_context()
    assert "terse replies" in ctx.agents_md


def test_seed_bundled_skills_seeds_macos_skills_on_macos(holo_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(customization, "bundled_skill_os", lambda: "macos")
    customization.seed_bundled_skills()
    seeded = {p.parent.name for p in customization.SKILLS_DIR.glob("*/SKILL.md")}
    assert {"apple-notes", "finder", "safari"} <= seeded
    assert {"file-explorer", "outlook", "edge", "windows-settings"}.isdisjoint(seeded)


def test_seed_bundled_skills_seeds_windows_skills_on_windows(holo_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(customization, "bundled_skill_os", lambda: "windows")
    customization.seed_bundled_skills()
    seeded = {p.parent.name for p in customization.SKILLS_DIR.glob("*/SKILL.md")}
    assert {"file-explorer", "outlook", "edge", "windows-settings"} <= seeded
    assert "safari" not in seeded
    assert not any(name.startswith("apple-") for name in seeded)


def test_seed_bundled_skills_seeds_chrome_body_for_the_host_os(
    holo_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`chrome` exists for both OSes; the seeded body must be the host-OS variant, not the other."""
    monkeypatch.setattr(customization, "bundled_skill_os", lambda: "windows")
    customization.seed_bundled_skills()
    chrome = (customization.SKILLS_DIR / "chrome" / "SKILL.md").read_text(encoding="utf-8")
    assert "Ctrl+T" in chrome


def test_bundled_skill_os_maps_supported_platforms(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(customization.platform, "system", lambda: "Darwin")
    assert customization.bundled_skill_os() == "macos"
    monkeypatch.setattr(customization.platform, "system", lambda: "Windows")
    assert customization.bundled_skill_os() == "windows"


def test_seed_bundled_skills_is_noop_on_unsupported_host(holo_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(customization.platform, "system", lambda: "Linux")
    customization.seed_bundled_skills()
    assert customization.bundled_skill_os() is None
    assert not list(customization.SKILLS_DIR.glob("*/SKILL.md"))


def test_skills_with_duplicate_kebab_slug_are_deduped(holo_home: Path) -> None:
    _write_skill(holo_home, "Apple-Mail", frontmatter="description: Mail (caps).", body="A")
    _write_skill(holo_home, "apple-mail", frontmatter="description: Mail (lower).", body="B")
    ctx = customization.load_agent_context()
    assert len(ctx.skills) == 1
    assert ctx.skills[0].name == "apple-mail"
