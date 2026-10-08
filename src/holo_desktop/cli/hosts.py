"""MCP hosts `holo install` wires the stdio `holo mcp` server into; the install engine is the SDK's."""

from __future__ import annotations

import os
import shutil
import sys
from importlib import resources
from pathlib import Path

from hai_agents_cli.mcp_hosts import Client, user_config_path

SERVER_NAME = "holo"
SKILL_NAME = "holo-desktop"
# Placeholder for the absolute `holo` path, filled at install time.
HOLO = "__HOLO__"
_LEAF = {"command": HOLO, "args": ["mcp"]}


def resolve_holo_command(*, path: str | None = None) -> str:
    """Absolute path to `holo`; baked into host configs so GUI hosts (Cursor, Claude Desktop, ...) hit the right binary even with a stripped PATH."""
    venv_bin = str(Path(sys.executable).parent)
    found = shutil.which("holo", path=venv_bin) or shutil.which("holo", path=path)
    if not found:
        raise RuntimeError(
            "Cannot resolve absolute path of 'holo' on this machine. "
            "Reinstall with `uv tool install holo-desktop-cli` or ensure 'holo' is on PATH, then re-run."
        )
    return os.path.realpath(found)


CODEX_APP_CLI = Path("/Applications/Codex.app/Contents/Resources/codex")


def codex_cli() -> str:
    """`codex` on PATH, else the CLI bundled in the Codex desktop app."""
    return str(CODEX_APP_CLI) if not shutil.which("codex") and CODEX_APP_CLI.exists() else "codex"


def skill_source() -> Path:
    return Path(str(resources.files("holo_desktop.host_skills").joinpath(SKILL_NAME)))


CLIENTS: dict[str, Client] = {
    "antigravity": Client(
        name="Antigravity (Google)",
        # Shared CLI+IDE config; a user-managed CLI-only override at ~/.gemini/antigravity-cli/mcp_config.json wins when present.
        config_path="~/.gemini/config/mcp_config.json",
        key_path=("mcpServers", SERVER_NAME),
        leaf=_LEAF,
    ),
    "claude-code": Client(
        name="Claude Code",
        cli_cmd=("claude", "mcp", "add", "--scope", "user", "--transport", "stdio", SERVER_NAME, "--", HOLO, "mcp"),
        cli_remove_cmds=(
            ("claude", "mcp", "remove", "--scope", "local", SERVER_NAME),
            ("claude", "mcp", "remove", "--scope", "user", SERVER_NAME),
        ),
        skills_dir=".claude/skills",
        home_marker=".claude",
    ),
    "claude-desktop": Client(
        name="Claude Desktop",
        config_path=user_config_path("Claude", "claude_desktop_config.json"),
        key_path=("mcpServers", SERVER_NAME),
        leaf=_LEAF,
    ),
    "codex": Client(
        name="Codex (OpenAI)",
        cli_cmd=(codex_cli(), "mcp", "add", SERVER_NAME, "--", HOLO, "mcp"),
        cli_remove_cmds=((codex_cli(), "mcp", "remove", SERVER_NAME),),
        skills_dir=".agents/skills",
        home_marker=".codex",
    ),
    "copilot": Client(
        name="GitHub Copilot CLI",
        config_path="~/.copilot/mcp-config.json",
        key_path=("mcpServers", SERVER_NAME),
        leaf={"type": "local", "command": HOLO, "args": ["mcp"], "tools": ["*"]},
    ),
    "cursor": Client(
        name="Cursor",
        config_path="~/.cursor/mcp.json",
        key_path=("mcpServers", SERVER_NAME),
        leaf={"type": "stdio", "command": HOLO, "args": ["mcp"]},
    ),
    "grok-build": Client(
        name="Grok Build (xAI)",
        cli_cmd=("grok", "mcp", "add", SERVER_NAME, "--", HOLO, "mcp"),
        cli_remove_cmds=(("grok", "mcp", "remove", "--scope", "user", SERVER_NAME),),
        skills_dir=".grok/skills",
        home_marker=".grok",
    ),
    "hermes": Client(
        name="Hermes (NousResearch)",
        config_path="~/.hermes/config.yaml",
        key_path=("mcp_servers", SERVER_NAME),
        leaf=_LEAF,
    ),
    "openclaw": Client(
        name="OpenClaw",
        config_path="~/.openclaw/openclaw.json",
        key_path=("mcp", "servers", SERVER_NAME),
        leaf=_LEAF,
        skills_dir=".openclaw/skills",
        home_marker=".openclaw",
    ),
    "opencode": Client(
        name="OpenCode",
        config_path="~/.config/opencode/opencode.json",
        key_path=("mcp", SERVER_NAME),
        leaf={"type": "local", "command": [HOLO, "mcp"], "enabled": True},
        skills_dir=".config/opencode/skills",
        home_marker=".config/opencode",
    ),
}
