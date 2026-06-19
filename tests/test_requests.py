"""Behavioural tests for ``build_session_request``: ``~/.holo`` inputs ride the inline ``Agent`` spec."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from agent_interface.specs.agent import Agent
from agent_interface.specs.session import SessionRequest
from agent_interface.specs.skill import Skill

from holo_desktop import customization
from holo_desktop.agent_client.requests import HOLO_AGENT_NAME, build_session_request


@pytest.fixture
def holo_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Re-point every customization path constant at a tmp dir (same pattern as test_customization)."""
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


def _write_skill(home: Path, slug: str, description: str, body: str) -> None:
    skill_path = home / "skills" / slug / "SKILL.md"
    skill_path.parent.mkdir(parents=True, exist_ok=True)
    skill_path.write_text(f"---\ndescription: {description}\n---\n\n{body}\n", encoding="utf-8")


def _inline_agent(request: SessionRequest) -> Agent:
    assert isinstance(request.agent, Agent)
    return request.agent


def test_bare_task_without_customization(holo_home: Path) -> None:
    request = build_session_request(task="say hi", max_steps=None, max_time_s=None)
    agent = _inline_agent(request)
    assert agent.name == HOLO_AGENT_NAME
    assert agent.instructions is None
    assert agent.skills is None
    assert request.messages == "say hi"
    assert request.max_steps is None
    assert request.max_time_s is None


def test_instructions_land_on_the_agent_spec_not_the_task(holo_home: Path) -> None:
    (holo_home / "agents.md").write_text("Always reply in English.\n", encoding="utf-8")
    (holo_home / "rules.md").write_text("Never close unsaved documents.\n", encoding="utf-8")

    request = build_session_request(task="say hi", max_steps=None, max_time_s=None)

    instructions = _inline_agent(request).instructions
    assert instructions is not None
    assert "Always reply in English." in instructions
    assert "- Never close unsaved documents." in instructions
    # The task stays bare: instructions reach the system prompt via the spec, not the user message.
    assert request.messages == "say hi"


def test_skills_are_inlined_into_the_agent_spec(holo_home: Path) -> None:
    _write_skill(holo_home, "safari", description="Drive the Safari browser.", body="Open Safari with Cmd+Space.")

    request = build_session_request(task="say hi", max_steps=None, max_time_s=None)

    skills = _inline_agent(request).skills
    assert skills is not None and len(skills) == 1
    skill = skills[0]
    assert isinstance(skill, Skill)
    assert skill.name == "safari"
    assert skill.body == "Open Safari with Cmd+Space."


def test_limits_pass_through(holo_home: Path) -> None:
    request = build_session_request(task="t", max_steps=30, max_time_s=120.0)
    assert request.max_steps == 30
    assert request.max_time_s == 120.0


def test_request_survives_a_wire_round_trip(holo_home: Path) -> None:
    (holo_home / "memories.md").write_text("User prefers dark mode.\n", encoding="utf-8")
    _write_skill(holo_home, "finder", description="Finder.", body="Cmd+N opens a new window.")
    request = build_session_request(task="say hi", max_steps=5, max_time_s=None)

    # What the client actually sends must validate server-side as a SessionRequest.
    payload = request.model_dump(mode="json", exclude_none=True)
    parsed = SessionRequest.model_validate(payload)

    agent = _inline_agent(parsed)
    assert agent.instructions is not None and "User prefers dark mode." in agent.instructions
    assert agent.skills is not None and [s.name for s in agent.skills if isinstance(s, Skill)] == ["finder"]
    assert parsed.message_list is not None
    assert parsed.message_list[0].message == "say hi"
