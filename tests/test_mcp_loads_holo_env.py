"""Behavioural test: `holo mcp` must load ``~/.holo/.env`` like acp/run/serve do.

A port (or token) stored in ``~/.holo/.env`` works for every other surface via
``load_holo_env()``; mcp skipping it would silently ignore the user's config.
"""

from __future__ import annotations

import importlib
import os
from pathlib import Path

import pytest

from holo_desktop import customization
from holo_desktop.agent_client.launcher import PORT_ENV
from holo_desktop.cli import bootstrap

# `holo_desktop.cli.__init__` re-exports the `mcp` command function under the
# same name as the submodule; go through importlib to get the module itself.
mcp_mod = importlib.import_module("holo_desktop.cli.mcp")


@pytest.mark.timeout(60)
def test_mcp_loads_holo_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    user_env = tmp_path / ".env"
    user_env.write_text(f"{PORT_ENV}=23456\n", encoding="utf-8")
    monkeypatch.setattr(bootstrap, "USER_ENV_PATH", user_env)
    monkeypatch.delenv(PORT_ENV, raising=False)
    # Keep skill seeding and the credential gate away from the real ~/.holo.
    monkeypatch.setattr(customization, "SKILLS_DIR", tmp_path / "skills")
    monkeypatch.setattr(customization, "SETTINGS_PATH", tmp_path / "settings.json")
    monkeypatch.setenv("HAI_API_KEY", "test-key")
    # The stdio server loop is not under test; stop at the bootstrap boundary.
    monkeypatch.setattr(mcp_mod.mcp_app, "run", lambda: None)

    mcp_mod.mcp()

    assert os.environ.get(PORT_ENV) == "23456"
