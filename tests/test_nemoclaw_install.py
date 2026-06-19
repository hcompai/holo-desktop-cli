"""Tests for the NemoClaw host install path."""

from __future__ import annotations

import json
import subprocess
import urllib.error
from importlib import resources
from pathlib import Path

from holo_desktop.cli import hosts
from holo_desktop.host_integrations.nemoclaw import install as nemoclaw_install


def test_default_nemoclaw_sandbox_prefers_default(monkeypatch) -> None:
    def fake_run(cmd: list[str], *, timeout: int) -> subprocess.CompletedProcess[str]:
        payload = {
            "defaultSandbox": "daily-driver",
            "lastOnboardedSandbox": "older",
            "sandboxes": [{"name": "fallback"}],
        }
        return subprocess.CompletedProcess(cmd, 0, json.dumps(payload), "")

    monkeypatch.setattr(nemoclaw_install, "_run_host_command", fake_run)

    assert nemoclaw_install._default_nemoclaw_sandbox("/usr/local/bin/nemoclaw") == "daily-driver"


def test_default_nemoclaw_sandbox_uses_only_single_unambiguous_sandbox(monkeypatch) -> None:
    def fake_run(cmd: list[str], *, timeout: int) -> subprocess.CompletedProcess[str]:
        payload = {"sandboxes": [{"name": "only-sandbox"}]}
        return subprocess.CompletedProcess(cmd, 0, json.dumps(payload), "")

    monkeypatch.setattr(nemoclaw_install, "_run_host_command", fake_run)

    assert nemoclaw_install._default_nemoclaw_sandbox("/usr/local/bin/nemoclaw") == "only-sandbox"


def test_default_nemoclaw_sandbox_rejects_ambiguous_sandbox_list(monkeypatch) -> None:
    def fake_run(cmd: list[str], *, timeout: int) -> subprocess.CompletedProcess[str]:
        payload = {"sandboxes": [{"name": "alpha"}, {"name": "beta"}]}
        return subprocess.CompletedProcess(cmd, 0, json.dumps(payload), "")

    monkeypatch.setattr(nemoclaw_install, "_run_host_command", fake_run)

    assert nemoclaw_install._default_nemoclaw_sandbox("/usr/local/bin/nemoclaw") is None


def test_nemoclaw_present_uses_cli_binary(monkeypatch) -> None:
    monkeypatch.setattr(nemoclaw_install.shutil, "which", lambda name: "/usr/local/bin/nemoclaw")
    monkeypatch.setattr(nemoclaw_install, "_default_nemoclaw_sandbox", lambda exe: "alpha")

    assert nemoclaw_install.nemoclaw_present()


def test_nemoclaw_policy_only_exposes_bridge_port() -> None:
    policy = nemoclaw_install._nemoclaw_policy_text()

    assert "port: 19131" in policy
    assert "19130" not in policy
    assert "path: /health" in policy
    assert "path: /run" not in policy
    assert "path: /launch" in policy
    assert "path: /poll" in policy
    assert "path: /kill" in policy
    assert "path: /home/linuxbrew/.linuxbrew/bin/node" in policy


def test_wire_nemoclaw_sets_up_default_sandbox(tmp_path: Path, monkeypatch) -> None:
    exe = "/usr/local/bin/nemoclaw"
    commands: list[list[str]] = []

    def fake_run(cmd: list[str], *, timeout: int) -> subprocess.CompletedProcess[str]:
        commands.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(nemoclaw_install, "_nemoclaw_dir", lambda: tmp_path / ".holo" / "nemoclaw")
    monkeypatch.delenv(nemoclaw_install.NEMOCLAW_SANDBOX_ENV, raising=False)
    monkeypatch.setattr(
        nemoclaw_install.shutil, "which", lambda name: exe if name == nemoclaw_install.NEMOCLAW_BINARY else None
    )
    monkeypatch.setattr(nemoclaw_install, "_default_nemoclaw_sandbox", lambda command: "alpha")
    monkeypatch.setattr(
        nemoclaw_install, "_ensure_nemoclaw_bridge", lambda token: (hosts.Status.INSTALLED, "bridge started on 19131")
    )
    monkeypatch.setattr(nemoclaw_install, "_run_host_command", fake_run)

    status, detail = nemoclaw_install.wire_nemoclaw()

    assert status is hosts.Status.INSTALLED
    assert "sandbox alpha" in detail
    assert "MCP registered" in detail
    assert (tmp_path / ".holo" / "nemoclaw" / "bridge-token").exists()
    assert commands[0][:5] == [exe, "sandbox", "policy", "add", "alpha"]
    assert commands[1][:5] == [exe, "sandbox", "skill", "install", "alpha"]
    assert "@modelcontextprotocol/sdk" in commands[2]
    assert nemoclaw_install.NEMOCLAW_MCP_PROXY_PATH in " ".join(commands[3])
    assert commands[4][:8] == [exe, "sandbox", "exec", "alpha", "--timeout", "30", "--", "python3"]
    mcp_command = commands[5]
    assert mcp_command[:8] == [exe, "sandbox", "exec", "alpha", "--timeout", "30", "--", "openclaw"]
    assert mcp_command[8:11] == ["mcp", "set", hosts.BINARY]
    mcp_config = json.loads(mcp_command[-1])
    token = mcp_config["env"]["HOLO_BRIDGE_TOKEN"]
    assert token
    assert token not in detail
    assert mcp_config["env"]["HOLO_BRIDGE_URL"] == "http://host.openshell.internal:19131"
    assert mcp_config["env"]["HOLO_BRIDGE_PORT"] == "19131"
    assert commands[6][:4] == [exe, "sandbox", "recover", "alpha"]


def test_wire_nemoclaw_preserves_sandbox_proxy_env(tmp_path: Path, monkeypatch) -> None:
    exe = "/usr/local/bin/nemoclaw"
    commands: list[list[str]] = []

    def fake_run(cmd: list[str], *, timeout: int) -> subprocess.CompletedProcess[str]:
        commands.append(cmd)
        if len(commands) == 5:
            return subprocess.CompletedProcess(cmd, 0, json.dumps({"HTTPS_PROXY": "http://proxy:8080"}), "")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(nemoclaw_install, "_nemoclaw_dir", lambda: tmp_path / ".holo" / "nemoclaw")
    monkeypatch.delenv(nemoclaw_install.NEMOCLAW_SANDBOX_ENV, raising=False)
    monkeypatch.setattr(
        nemoclaw_install.shutil, "which", lambda name: exe if name == nemoclaw_install.NEMOCLAW_BINARY else None
    )
    monkeypatch.setattr(nemoclaw_install, "_default_nemoclaw_sandbox", lambda command: "alpha")
    monkeypatch.setattr(
        nemoclaw_install, "_ensure_nemoclaw_bridge", lambda token: (hosts.Status.INSTALLED, "bridge started on 19131")
    )
    monkeypatch.setattr(nemoclaw_install, "_run_host_command", fake_run)

    status, _ = nemoclaw_install.wire_nemoclaw()

    assert status is hosts.Status.INSTALLED
    mcp_config = json.loads(commands[5][-1])
    assert mcp_config["env"]["HTTPS_PROXY"] == "http://proxy:8080"
    assert mcp_config["env"]["NODE_USE_ENV_PROXY"] == "1"


def test_nemoclaw_proxy_is_packaged() -> None:
    proxy = resources.files("holo_desktop.host_integrations.nemoclaw").joinpath("holo_mcp_bridge.mjs")
    text = proxy.read_text(encoding="utf-8")

    assert "holo_desktop_launch" in text
    assert "holo_desktop_poll" in text
    assert "holo_desktop_kill" in text
    assert "media_paths" in text
    assert "media://" in text
    assert 'mediaPath.startsWith("media://")' in text
    assert "fs.realpath(openClawMediaRoot)" in text
    assert "isWithinMediaRoot" in text
    assert "holo_desktop_poll again with the same run_id" in text
    assert text.count("try {") >= 3
    assert "Preferred for ordinary user requests" not in text


def test_bridge_port_conflict_reports_auth_mismatch(monkeypatch) -> None:
    def fake_urlopen(request, *, timeout: int):
        raise urllib.error.HTTPError(
            url=request.full_url,
            code=401,
            msg="unauthorized",
            hdrs={},
            fp=None,
        )

    monkeypatch.setattr(nemoclaw_install.urllib.request, "urlopen", fake_urlopen)

    conflict = nemoclaw_install._nemoclaw_bridge_port_conflict()

    assert conflict is not None
    assert "saved token did not authorize" in conflict


def test_holo_skill_mentions_lazy_discovery_and_media_paths() -> None:
    skill = resources.files("holo_desktop.host_skills").joinpath("holo-desktop", "SKILL.md")
    text = skill.read_text(encoding="utf-8")

    assert "search for holo_desktop tools" in text
    assert "That is not a blocker" in text
    assert "media_paths" in text
    assert "media://inbound/<receipt>.jpg" in text
    assert "call `holo_desktop_launch` once" in text
    assert "poll the same `run_id` again" in text
    assert "Do not ask Holo to upload" in text
    assert "source of truth" in text
    assert "stale images visible in chat history" in text
