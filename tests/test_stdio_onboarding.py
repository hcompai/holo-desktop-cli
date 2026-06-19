"""Behavioural tests: `holo mcp` / `holo acp` onboarding parity with run/serve.

A user whose first touchpoint is an MCP/ACP host must still get bundled skills
seeded, and a missing credential must fail fast with a `holo login` pointer —
stdio servers cannot open a browser, and the binary's own failure is cryptic.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from holo_desktop import customization
from holo_desktop.cli import bootstrap

# `holo_desktop.cli.__init__` re-exports the command functions under the same
# names as their submodules; go through importlib to get the modules.
mcp_mod = importlib.import_module("holo_desktop.cli.mcp")
acp_mod = importlib.import_module("holo_desktop.cli.acp")


@pytest.fixture()
def holo_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(customization, "SKILLS_DIR", tmp_path / "skills")
    monkeypatch.setattr(customization, "SETTINGS_PATH", tmp_path / "settings.json")
    monkeypatch.setattr(bootstrap, "USER_ENV_PATH", tmp_path / ".env")
    monkeypatch.delenv("HAI_API_KEY", raising=False)
    monkeypatch.delenv("HAI_AGENT_RUNTIME_BASE_URL", raising=False)
    monkeypatch.delenv("HAI_AGENT_RUNTIME_FAKE", raising=False)
    return tmp_path


def _stub_mcp_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mcp_mod.mcp_app, "run", lambda: None)


def _stub_acp_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_run_agent(agent: object) -> None:
        return

    monkeypatch.setattr(acp_mod, "run_agent", fake_run_agent)


@pytest.mark.timeout(60)
def test_mcp_seeds_bundled_skills(holo_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAI_API_KEY", "key")
    # Seeding parity is only observable where a bundled set ships; pin one so the
    # assertion holds on any runner (Linux has no bundled set, seeding no-ops there).
    monkeypatch.setattr(customization, "bundled_skill_os", lambda: "macos")
    _stub_mcp_loop(monkeypatch)

    mcp_mod.mcp()

    seeded = list((holo_home / "skills").glob("*/SKILL.md"))
    assert seeded, "mcp must seed bundled skills like run/serve do"


@pytest.mark.timeout(60)
def test_acp_seeds_bundled_skills(holo_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAI_API_KEY", "key")
    # Seeding parity is only observable where a bundled set ships; pin one so the
    # assertion holds on any runner (Linux has no bundled set, seeding no-ops there).
    monkeypatch.setattr(customization, "bundled_skill_os", lambda: "macos")
    _stub_acp_loop(monkeypatch)

    acp_mod.acp()

    seeded = list((holo_home / "skills").glob("*/SKILL.md"))
    assert seeded, "acp must seed bundled skills like run/serve do"


@pytest.mark.timeout(60)
def test_acp_announces_beta_on_stderr(
    holo_home: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # ACP is beta; the notice must reach stderr (stdout carries the protocol).
    monkeypatch.setenv("HAI_API_KEY", "key")
    _stub_acp_loop(monkeypatch)

    acp_mod.acp()

    captured = capsys.readouterr()
    assert "beta" in captured.err.lower()
    assert "beta" not in captured.out.lower()


@pytest.mark.timeout(60)
def test_mcp_without_credentials_fails_fast_with_login_hint(
    holo_home: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _stub_mcp_loop(monkeypatch)

    with pytest.raises(SystemExit) as excinfo:
        mcp_mod.mcp()

    assert excinfo.value.code == 1
    assert "holo login" in capsys.readouterr().err


@pytest.mark.timeout(60)
def test_acp_without_credentials_fails_fast_with_login_hint(
    holo_home: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _stub_acp_loop(monkeypatch)

    with pytest.raises(SystemExit) as excinfo:
        acp_mod.acp()

    assert excinfo.value.code == 1
    assert "holo login" in capsys.readouterr().err


@pytest.mark.timeout(60)
@pytest.mark.parametrize(
    ("env_name", "env_value"),
    [("HAI_AGENT_RUNTIME_BASE_URL", "http://localhost:8000/v1"), ("HAI_AGENT_RUNTIME_FAKE", "1")],
)
def test_mcp_runs_without_key_in_self_hosted_or_fake_mode(
    holo_home: Path, monkeypatch: pytest.MonkeyPatch, env_name: str, env_value: str
) -> None:
    monkeypatch.setenv(env_name, env_value)
    _stub_mcp_loop(monkeypatch)

    mcp_mod.mcp()  # must not raise
