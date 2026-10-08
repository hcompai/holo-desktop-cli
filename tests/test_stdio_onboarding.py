"""`holo mcp` onboarding: skills seed, and a missing credential fails fast with a `holo login` pointer."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from holo_desktop import customization

# `holo_desktop.cli.__init__` re-exports the command functions under the same
# names as their submodules; go through importlib to get the module.
mcp_mod = importlib.import_module("holo_desktop.cli.mcp")


@pytest.fixture()
def holo_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(customization, "SKILLS_DIR", tmp_path / "skills")
    monkeypatch.setattr(customization, "SETTINGS_PATH", tmp_path / "settings.json")
    monkeypatch.setattr(mcp_mod.mcp_app, "run", lambda: None)
    return tmp_path


def test_mcp_seeds_bundled_skills(holo_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAI_API_KEY", "key")
    # Linux ships no bundled set, so pin one to keep the assertion meaningful on any runner.
    monkeypatch.setattr(customization, "bundled_skill_os", lambda: "macos")

    mcp_mod.mcp()

    assert list((holo_home / "skills").glob("*/SKILL.md"))


def test_mcp_without_credentials_fails_fast_with_login_hint(
    holo_home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as excinfo:
        mcp_mod.mcp()

    assert excinfo.value.code == 1
    assert "holo login" in capsys.readouterr().err


def test_mcp_runs_without_key_against_a_self_hosted_model(holo_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAI_AGENT_RUNTIME_BASE_URL", "http://localhost:8000/v1")
    monkeypatch.setenv("HAI_AGENT_RUNTIME_MODEL", "holo3")

    mcp_mod.mcp()
