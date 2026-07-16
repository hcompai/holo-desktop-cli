"""Behavioural tests for `holo install`: host wiring + skill auto-wire + dispatch.

Every host config and skill dir is sandboxed under a tmp ``$HOME``; the real
`holo` binary is faked. The three wiring strategies (JSON merge, YAML merge,
CLI add) and the skill symlink are exercised against a real filesystem, and the
`install()` dispatcher's invocation matrix (one host, all detected, list,
unknown, the `mcp`/`acp` redirects) is checked end to end including exit codes.
"""

from __future__ import annotations

import importlib
import json
import subprocess
from pathlib import Path

import pytest
import yaml

from holo_desktop.cli import hosts

# `holo_desktop.cli.__init__` re-exports `install` under the submodule name; go
# through importlib for the module so we reach `install.install`.
install_mod = importlib.import_module("holo_desktop.cli.install")

FAKE_HOLO = "/fake/bin/holo"


@pytest.fixture()
def sandbox_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point `$HOME` (and Windows `USERPROFILE`) at tmp and fake the `holo` path."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setattr(hosts, "resolve_holo_command", lambda: FAKE_HOLO)
    return tmp_path


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# JSON-merge strategy (cursor, opencode, copilot, ...)
# --------------------------------------------------------------------------- #


def test_json_host_fresh_write_materializes_absolute_binary(sandbox_home: Path) -> None:
    status, _ = hosts.wire_mcp(hosts.CLIENTS["cursor"])
    assert status is hosts.Status.INSTALLED

    cfg = _read_json(sandbox_home / ".cursor" / "mcp.json")
    leaf = cfg["mcpServers"]["holo"]
    assert leaf == {"type": "stdio", "command": FAKE_HOLO, "args": ["mcp"]}


def test_json_host_with_list_command_materializes_binary(sandbox_home: Path) -> None:
    # opencode's leaf carries the binary inside a `command: [...]` list.
    hosts.wire_mcp(hosts.CLIENTS["opencode"])
    cfg = _read_json(sandbox_home / ".config" / "opencode" / "opencode.json")
    assert cfg["mcp"]["holo"]["command"] == [FAKE_HOLO, "mcp"]


def test_json_host_preserves_sibling_servers(sandbox_home: Path) -> None:
    path = sandbox_home / ".cursor" / "mcp.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"mcpServers": {"other": {"command": "x"}}}), encoding="utf-8")

    hosts.wire_mcp(hosts.CLIENTS["cursor"])

    cfg = _read_json(path)
    assert cfg["mcpServers"]["other"] == {"command": "x"}
    assert "holo" in cfg["mcpServers"]


def test_json_host_idempotent_rerun_skips(sandbox_home: Path) -> None:
    client = hosts.CLIENTS["cursor"]
    assert hosts.wire_mcp(client)[0] is hosts.Status.INSTALLED
    assert hosts.wire_mcp(client)[0] is hosts.Status.SKIPPED


def test_json_host_malformed_config_fails_without_clobber(sandbox_home: Path) -> None:
    path = sandbox_home / ".cursor" / "mcp.json"
    path.parent.mkdir(parents=True)
    path.write_text("{ not json", encoding="utf-8")

    status, detail = hosts.wire_mcp(hosts.CLIENTS["cursor"])
    assert status is hosts.Status.FAILED
    assert "invalid config" in detail
    assert path.read_text(encoding="utf-8") == "{ not json"  # untouched


def test_json_host_backs_up_before_rewrite(sandbox_home: Path) -> None:
    path = sandbox_home / ".cursor" / "mcp.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"mcpServers": {"other": {"command": "x"}}}), encoding="utf-8")

    hosts.wire_mcp(hosts.CLIENTS["cursor"])

    backup = path.with_name(path.name + ".holo.bak")
    assert backup.exists()
    assert _read_json(backup) == {"mcpServers": {"other": {"command": "x"}}}


# --------------------------------------------------------------------------- #
# YAML-merge strategy (hermes)
# --------------------------------------------------------------------------- #


def test_yaml_host_fresh_write(sandbox_home: Path) -> None:
    status, _ = hosts.wire_mcp(hosts.CLIENTS["hermes"])
    assert status is hosts.Status.INSTALLED

    cfg = yaml.safe_load((sandbox_home / ".hermes" / "config.yaml").read_text(encoding="utf-8"))
    assert cfg["mcp_servers"]["holo"] == {"command": FAKE_HOLO, "args": ["mcp"]}


def test_yaml_empty_file_treated_as_empty_mapping(sandbox_home: Path) -> None:
    path = sandbox_home / ".hermes" / "config.yaml"
    path.parent.mkdir(parents=True)
    path.write_text("# just a comment\n", encoding="utf-8")

    assert hosts.wire_mcp(hosts.CLIENTS["hermes"])[0] is hosts.Status.INSTALLED
    cfg = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert cfg["mcp_servers"]["holo"]["command"] == FAKE_HOLO


def test_yaml_non_mapping_top_level_fails(sandbox_home: Path) -> None:
    path = sandbox_home / ".hermes" / "config.yaml"
    path.parent.mkdir(parents=True)
    path.write_text("- a\n- b\n", encoding="utf-8")

    status, detail = hosts.wire_mcp(hosts.CLIENTS["hermes"])
    assert status is hosts.Status.FAILED
    assert "not a mapping" in detail


def test_hermes_ships_no_skill(sandbox_home: Path) -> None:
    # Hermes auto-loads no skills: install must wire MCP only, never a skill dir.
    assert hosts.CLIENTS["hermes"].skills_dir is None
    status, detail = hosts.wire_skill(hosts.CLIENTS["hermes"])
    assert status is hosts.Status.SKIPPED
    assert "no skill" in detail


# --------------------------------------------------------------------------- #
# CLI-add strategy (claude-code, codex)
# --------------------------------------------------------------------------- #


def _stub_cli(monkeypatch: pytest.MonkeyPatch, *, result: object) -> list[list[str]]:
    """Fake `which`/`run`; return a list that captures the resolved argv per call."""
    calls: list[list[str]] = []
    monkeypatch.setattr(hosts.shutil, "which", lambda name: f"/usr/local/bin/{name}")

    def fake_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        if isinstance(result, Exception):
            raise result
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(hosts.subprocess, "run", fake_run)
    return calls


def test_cli_host_success(sandbox_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _stub_cli(monkeypatch, result=None)
    status, _ = hosts.wire_mcp(hosts.CLIENTS["claude-code"])
    assert status is hosts.Status.INSTALLED
    assert calls, "expected the host CLI to be invoked"


def test_cli_rewrites_binary_only_after_separator(sandbox_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _stub_cli(monkeypatch, result=None)
    hosts.wire_mcp(hosts.CLIENTS["claude-code"])
    argv = calls[0]
    sep = argv.index("--")
    # The server label before `--` stays the bare name; the command after is absolute.
    assert "holo" in argv[:sep]
    assert FAKE_HOLO not in argv[:sep]
    assert argv[sep + 1] == FAKE_HOLO


def test_cli_host_already_wired_skips(sandbox_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    err = subprocess.CalledProcessError(1, ["claude"], stderr="server 'holo' already exists")
    _stub_cli(monkeypatch, result=err)
    status, _ = hosts.wire_mcp(hosts.CLIENTS["claude-code"])
    assert status is hosts.Status.SKIPPED


def test_cli_host_real_failure_is_fatal(sandbox_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    err = subprocess.CalledProcessError(1, ["claude"], stderr="connection refused")
    _stub_cli(monkeypatch, result=err)
    status, detail = hosts.wire_mcp(hosts.CLIENTS["claude-code"])
    assert status is hosts.Status.FAILED
    assert status.fatal
    assert "connection refused" in detail


def test_cli_host_absent_when_binary_missing(sandbox_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hosts.shutil, "which", lambda name: None)
    status, _ = hosts.wire_mcp(hosts.CLIENTS["claude-code"])
    assert status is hosts.Status.ABSENT


def test_grok_build_is_registered_as_cli_host() -> None:
    client = hosts.CLIENTS["grok-build"]

    assert client.cli_cmd == ("grok", "mcp", "add", "holo", "--", "holo", "mcp")
    assert client.skills_dir == ".grok/skills"
    assert client.home_marker == ".grok"
    assert client.config_path is None


def test_grok_build_cli_add_rewrites_binary_after_separator(
    sandbox_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _stub_cli(monkeypatch, result=None)
    status, _ = hosts.wire_mcp(hosts.CLIENTS["grok-build"])
    assert status is hosts.Status.INSTALLED

    argv = calls[0]
    assert argv[0] == "/usr/local/bin/grok"
    sep = argv.index("--")
    # The server name before `--` stays bare; `grok mcp add` upserts, so reruns exit 0.
    assert argv[:sep] == ["/usr/local/bin/grok", "mcp", "add", "holo"]
    assert argv[sep + 1 :] == [FAKE_HOLO, "mcp"]


def test_custom_wire_host_delegates_without_generic_mcp_or_skill(sandbox_home: Path) -> None:
    calls: list[str] = []
    client = hosts.Client(
        name="Custom",
        skills_dir=".custom/skills",
        wire=lambda: calls.append("wire") or (hosts.Status.INSTALLED, "custom wired"),
    )

    status, detail = hosts.wire_host(client)

    assert status is hosts.Status.INSTALLED
    assert detail == "custom wired"
    assert calls == ["wire"]
    assert not (sandbox_home / ".custom").exists()


def test_nemoclaw_is_registered_as_custom_host() -> None:
    client = hosts.CLIENTS["nemoclaw"]

    assert client.wire is not None
    assert client.target == "default NemoClaw sandbox"
    assert client.config_path is None
    assert hosts.host_target(client) == "default NemoClaw sandbox"


# --------------------------------------------------------------------------- #
# Skill auto-wire
# --------------------------------------------------------------------------- #


def _seed_marker(home: Path, client: hosts.Client) -> None:
    (home / (client.home_marker or "")).mkdir(parents=True, exist_ok=True)


def test_skill_symlink_created_when_host_present(sandbox_home: Path) -> None:
    client = hosts.CLIENTS["claude-code"]
    _seed_marker(sandbox_home, client)

    status, _ = hosts.wire_skill(client)
    assert status is hosts.Status.INSTALLED

    link = sandbox_home / client.skills_dir / hosts.SKILL_NAME
    assert link.is_symlink()
    assert (link / "SKILL.md").exists()


def test_skill_idempotent_rerun_skips(sandbox_home: Path) -> None:
    client = hosts.CLIENTS["claude-code"]
    _seed_marker(sandbox_home, client)
    assert hosts.wire_skill(client)[0] is hosts.Status.INSTALLED
    assert hosts.wire_skill(client)[0] is hosts.Status.SKIPPED


def test_grok_build_skill_symlink_created_when_host_present(sandbox_home: Path) -> None:
    client = hosts.CLIENTS["grok-build"]
    _seed_marker(sandbox_home, client)

    status, _ = hosts.wire_skill(client)
    assert status is hosts.Status.INSTALLED

    # Grok Build's skill walker follows symlinks (`Path::is_dir()`), so a link is enough.
    link = sandbox_home / ".grok" / "skills" / hosts.SKILL_NAME
    assert link.is_symlink()
    assert (link / "SKILL.md").exists()


def test_skill_absent_when_host_not_installed(sandbox_home: Path) -> None:
    # No marker dir seeded → host considered not installed → skill skipped, not failed.
    status, detail = hosts.wire_skill(hosts.CLIENTS["claude-code"])
    assert status is hosts.Status.ABSENT
    assert "not installed" in detail


def test_skill_foreign_entry_at_link_path_fails(sandbox_home: Path) -> None:
    # A non-skill entry squatting the link path must fail loudly, not be clobbered.
    client = hosts.CLIENTS["claude-code"]
    _seed_marker(sandbox_home, client)
    link = sandbox_home / client.skills_dir / hosts.SKILL_NAME
    link.parent.mkdir(parents=True)
    link.write_text("not a skill at all", encoding="utf-8")

    status, detail = hosts.wire_skill(client)
    assert status is hosts.Status.FAILED
    assert "not a holo skill" in detail


# --------------------------------------------------------------------------- #
# Detection
# --------------------------------------------------------------------------- #


def test_host_present_via_home_marker(sandbox_home: Path) -> None:
    client = hosts.CLIENTS["claude-code"]
    assert not hosts.host_present(client)
    _seed_marker(sandbox_home, client)
    assert hosts.host_present(client)


def test_host_present_via_config_parent(sandbox_home: Path) -> None:
    client = hosts.CLIENTS["cursor"]
    assert not hosts.host_present(client)
    (sandbox_home / ".cursor").mkdir()
    assert hosts.host_present(client)


# --------------------------------------------------------------------------- #
# install() dispatcher matrix
# --------------------------------------------------------------------------- #


def test_install_list_shows_supported_hosts(sandbox_home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    install_mod.install("list")
    out = capsys.readouterr().err
    assert "cursor" in out and "hermes" in out


def test_install_unknown_host_exits_2(sandbox_home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        install_mod.install("nope")
    assert exc.value.code == 2
    assert "unknown host" in capsys.readouterr().err


@pytest.mark.parametrize("alias", ["mcp", "acp"])
def test_install_protocol_word_redirects(sandbox_home: Path, capsys: pytest.CaptureFixture[str], alias: str) -> None:
    # `holo install mcp` / `holo install acp` are a natural mistype; they must
    # not read as a bare "unknown host" but point at the real commands.
    with pytest.raises(SystemExit) as exc:
        install_mod.install(alias)
    err = capsys.readouterr().err
    assert exc.value.code == 2
    assert "unknown host" not in err
    assert f"holo {alias}" in err
    assert "holo install <host>" in err or "holo install list" in err


def test_install_no_hosts_detected_exits_1(sandbox_home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        install_mod.install(None)
    assert exc.value.code == 1
    assert "No supported hosts" in capsys.readouterr().err


def test_install_single_host_writes_config(sandbox_home: Path) -> None:
    install_mod.install("cursor")
    assert (sandbox_home / ".cursor" / "mcp.json").exists()


def test_install_all_detected_wires_each_present_host(sandbox_home: Path) -> None:
    (sandbox_home / ".cursor").mkdir()
    (sandbox_home / ".hermes").mkdir()

    install_mod.install(None)

    assert (sandbox_home / ".cursor" / "mcp.json").exists()
    assert (sandbox_home / ".hermes" / "config.yaml").exists()
