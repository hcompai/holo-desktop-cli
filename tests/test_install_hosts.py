"""`holo install`: every detected host gets the stdio server at the absolute `holo` path, plus the skill."""

from __future__ import annotations

import importlib
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml
from hai_agents_cli import mcp_hosts

from holo_desktop.cli import hosts

# `holo_desktop.cli.__init__` re-exports `install` under the submodule name.
install_mod = importlib.import_module("holo_desktop.cli.install")

FAKE_HOLO = "/fake/bin/holo"


@pytest.fixture()
def sandbox_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setattr(install_mod, "resolve_holo_command", lambda: FAKE_HOLO)
    monkeypatch.setattr(mcp_hosts.shutil, "which", lambda name, **_: None)
    return tmp_path


def test_install_wires_every_detected_host_at_the_absolute_holo_path(sandbox_home: Path) -> None:
    for marker in (".cursor", ".hermes", ".config/opencode"):
        (sandbox_home / marker).mkdir(parents=True)

    install_mod.install(None)

    cursor = json.loads((sandbox_home / ".cursor" / "mcp.json").read_text())
    assert cursor["mcpServers"]["holo"] == {"type": "stdio", "command": FAKE_HOLO, "args": ["mcp"]}
    hermes = yaml.safe_load((sandbox_home / ".hermes" / "config.yaml").read_text())
    assert hermes["mcp_servers"]["holo"] == {"command": FAKE_HOLO, "args": ["mcp"]}
    opencode = json.loads((sandbox_home / ".config" / "opencode" / "opencode.json").read_text())
    assert opencode["mcp"]["holo"]["command"] == [FAKE_HOLO, "mcp"]
    skill = sandbox_home / ".config" / "opencode" / "skills" / "holo-desktop" / "SKILL.md"
    assert skill.exists()


def test_claude_code_is_rewired_at_user_scope(sandbox_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(mcp_hosts.shutil, "which", lambda name, **_: f"/usr/bin/{name}")

    def fake_run(cmd: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(mcp_hosts.subprocess, "run", fake_run)

    install_mod.install("claude-code")

    *removes, add = calls
    assert [rm[1:3] for rm in removes] == [["mcp", "remove"], ["mcp", "remove"]]
    assert add[1:] == ["mcp", "add", "--scope", "user", "--transport", "stdio", "holo", "--", FAKE_HOLO, "mcp"]


def test_codex_desktop_app_is_wired_through_its_bundled_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    app_cli = tmp_path / "codex"
    app_cli.touch()
    monkeypatch.setattr(hosts, "CODEX_APP_CLI", app_cli)
    monkeypatch.setattr(hosts.shutil, "which", lambda name, **_: None)

    assert hosts.codex_cli() == str(app_cli)


def test_install_rejects_bad_targets(sandbox_home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    for target, code, hint in (("nope", 2, "unknown host"), ("mcp", 2, "holo mcp"), (None, 1, "No supported hosts")):
        with pytest.raises(SystemExit) as exc:
            install_mod.install(target)
        assert exc.value.code == code
        assert hint in capsys.readouterr().err
