"""MCP-capable host registry + install dispatch + skill auto-wire. Add a host = add one `Client` entry."""

import contextlib
import enum
import json
import os
import platform
import shutil
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from importlib import resources
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

from holo_desktop.fs import atomic_write_text

BINARY = "holo"
SKILL_NAME = "holo-desktop"


def resolve_holo_command(*, path: str | None = None) -> str:
    """Absolute path to `holo`; baked into host configs so GUI hosts (Cursor, Claude Desktop, ...) hit the right binary even with a stripped PATH."""
    venv_bin = str(Path(sys.executable).parent)
    found = shutil.which(BINARY, path=venv_bin) or shutil.which(BINARY, path=path)
    if not found:
        raise RuntimeError(
            f"Cannot resolve absolute path of {BINARY!r} on this machine. "
            f"Reinstall with `uv tool install holo-desktop-cli` or ensure {BINARY!r} is on PATH, then re-run."
        )
    return os.path.realpath(found)


MCP_LEAF: dict[str, object] = {"command": BINARY, "args": ["mcp"]}


class Status(enum.Enum):
    """Outcome of one install step."""

    INSTALLED = "installed"
    SKIPPED = "skipped"
    ABSENT = "absent"
    FAILED = "failed"

    @property
    def ok(self) -> bool:
        """True if the operation succeeded or was already in place."""
        return self in (Status.INSTALLED, Status.SKIPPED)

    @property
    def fatal(self) -> bool:
        """True only for hard failures the user needs to act on."""
        return self is Status.FAILED


def home_short(p: Path | str) -> str:
    """Render `p` with $HOME collapsed to `~`."""
    s = str(p)
    home = str(Path.home())
    return "~" + s[len(home) :] if s.startswith(home) else s


@dataclass(frozen=True)
class Client:
    """One MCP host entry; heavyweight hosts can provide custom hooks."""

    name: str
    config_path: str | None = None
    cli_cmd: tuple[str, ...] | None = None
    key_path: tuple[str, ...] | None = None
    leaf: dict[str, object] | None = None
    skills_dir: str | None = None  # under $HOME; None if host doesn't auto-load skills
    home_marker: str | None = None  # under $HOME; presence proves the host is installed
    wire: Callable[[], tuple[Status, str]] | None = None
    present: Callable[[], bool] | None = None
    target: str | None = None


def _wire_nemoclaw() -> tuple[Status, str]:
    from holo_desktop.host_integrations.nemoclaw.install import wire_nemoclaw

    return wire_nemoclaw()


def _nemoclaw_present() -> bool:
    from holo_desktop.host_integrations.nemoclaw.install import nemoclaw_present

    return nemoclaw_present()


def install_via_cli(cmd: list[str]) -> tuple[Status, str]:
    exe = shutil.which(cmd[0])
    if exe is None:
        return Status.ABSENT, f"{cmd[0]!r} not on PATH"
    # Windows can't `CreateProcess` a `.cmd` shim directly; resolve via PATH.
    resolved = [exe, *cmd[1:]]
    # Before `--` is the host's server label (stays bare); after, `BINARY` must be absolute.
    try:
        sep = resolved.index("--")
    except ValueError:
        sep = len(resolved)
    holo = resolve_holo_command()
    resolved = resolved[:sep] + [holo if a == BINARY else a for a in resolved[sep:]]
    try:
        subprocess.run(resolved, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        msg = (exc.stderr or exc.stdout or str(exc)).strip()
        low = msg.lower()
        if any(marker in low for marker in ("already", "exists", "duplicate")):
            return Status.SKIPPED, f"{cmd[0]} already wired"
        return Status.FAILED, msg
    return Status.INSTALLED, f"via {cmd[0]} CLI"


def _materialize_leaf(leaf: dict[str, object]) -> dict[str, object]:
    """Substitute `BINARY` placeholders in `command`/`args`/`command:[...]` with the absolute path."""
    holo = resolve_holo_command()
    out: dict[str, object] = dict(leaf)
    for k, v in list(out.items()):
        if k == "command" and isinstance(v, str) and v == BINARY:
            out[k] = holo
        elif (k == "command" or k == "args") and isinstance(v, list):
            out[k] = [holo if a == BINARY else a for a in v]
    return out


def wire_mcp(c: Client) -> tuple[Status, str]:
    """Apply `c`'s install spec: CLI add, JSON merge, or YAML merge."""
    if c.cli_cmd is not None:
        return install_via_cli(list(c.cli_cmd))
    assert c.config_path is not None and c.key_path is not None and c.leaf is not None
    is_yaml = c.config_path.endswith((".yaml", ".yml"))
    path = Path(c.config_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    data: dict[str, object] = {}
    if path.exists() and path.stat().st_size > 0:
        try:
            loaded = (
                yaml.safe_load(path.read_text(encoding="utf-8"))
                if is_yaml
                else json.loads(path.read_text(encoding="utf-8"))
            )
        except (json.JSONDecodeError, yaml.YAMLError) as exc:
            return Status.FAILED, f"{path}: invalid config ({exc})"
        # YAML safe_load returns None for empty/comments-only files; treat as empty mapping.
        if loaded is not None and not isinstance(loaded, dict):
            return Status.FAILED, f"{path}: top-level is not a mapping"
        data = loaded or {}

    cursor: Any = data  # YAML descent: any node may be a scalar mid-walk; isinstance guards below.
    for k in c.key_path[:-1]:
        cursor = cursor.setdefault(k, {})
        if not isinstance(cursor, dict):
            return Status.FAILED, f"{path}: {k!r} is not an object"
    last = c.key_path[-1]
    existing = cursor.get(last)
    leaf = _materialize_leaf(c.leaf)
    merged = {**existing, **leaf} if isinstance(existing, dict) else leaf
    if existing == merged:
        return Status.SKIPPED, home_short(path)
    cursor[last] = merged
    dumped = (
        yaml.safe_dump(data, sort_keys=False, default_flow_style=False)
        if is_yaml
        else json.dumps(data, indent=2) + "\n"
    )
    _backup_config(path)
    atomic_write_text(path, dumped)
    return Status.INSTALLED, home_short(path)


def wire_host(c: Client) -> tuple[Status, str]:
    """Wire a standard MCP host or delegate to a host-specific installer."""
    if c.wire is not None:
        return c.wire()
    return wire_mcp(c)


def _backup_config(path: Path) -> None:
    """Snapshot an existing host config beside it before we rewrite it, so a bad merge is recoverable."""
    if path.exists():
        with contextlib.suppress(OSError):
            shutil.copy2(path, path.with_name(path.name + ".holo.bak"))


def _claude_desktop_config_path() -> str:
    """Per-OS Claude Desktop config: macOS `~/Library/...`, Windows `%APPDATA%`, Linux `~/.config/Claude/`."""
    system = platform.system()
    if system == "Windows":
        appdata = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return str(Path(appdata) / "Claude" / "claude_desktop_config.json")
    if system == "Darwin":
        return "~/Library/Application Support/Claude/claude_desktop_config.json"
    xdg = os.environ.get("XDG_CONFIG_HOME") or "~/.config"
    return f"{xdg}/Claude/claude_desktop_config.json"


CLIENTS: dict[str, Client] = {
    "antigravity": Client(
        name="Antigravity (Google)",
        # Shared CLI+IDE config; a user-managed CLI-only override at ~/.gemini/antigravity-cli/mcp_config.json wins when present.
        config_path="~/.gemini/config/mcp_config.json",
        key_path=("mcpServers", BINARY),
        leaf=MCP_LEAF,
    ),
    "claude-code": Client(
        name="Claude Code",
        cli_cmd=("claude", "mcp", "add", "--transport", "stdio", BINARY, "--", BINARY, "mcp"),
        skills_dir=".claude/skills",
        home_marker=".claude",
    ),
    "claude-desktop": Client(
        name="Claude Desktop",
        config_path=_claude_desktop_config_path(),
        key_path=("mcpServers", BINARY),
        leaf=MCP_LEAF,
    ),
    "codex": Client(
        name="Codex (OpenAI)",
        cli_cmd=("codex", "mcp", "add", BINARY, "--", BINARY, "mcp"),
        skills_dir=".agents/skills",
        home_marker=".codex",
    ),
    "copilot": Client(
        name="GitHub Copilot CLI",
        config_path="~/.copilot/mcp-config.json",
        key_path=("mcpServers", BINARY),
        leaf={"type": "local", "command": BINARY, "args": ["mcp"], "tools": ["*"]},
    ),
    "cursor": Client(
        name="Cursor",
        config_path="~/.cursor/mcp.json",
        key_path=("mcpServers", BINARY),
        leaf={"type": "stdio", "command": BINARY, "args": ["mcp"]},
    ),
    "hermes": Client(
        name="Hermes (NousResearch)",
        config_path="~/.hermes/config.yaml",
        key_path=("mcp_servers", BINARY),
        leaf=MCP_LEAF,
    ),
    "openclaw": Client(
        name="OpenClaw",
        config_path="~/.openclaw/openclaw.json",
        key_path=("mcp", "servers", BINARY),
        leaf=MCP_LEAF,
        skills_dir=".openclaw/skills",
        home_marker=".openclaw",
    ),
    "nemoclaw": Client(
        name="NemoClaw",
        present=_nemoclaw_present,
        target="default NemoClaw sandbox",
        wire=_wire_nemoclaw,
    ),
    "opencode": Client(
        name="OpenCode",
        config_path="~/.config/opencode/opencode.json",
        key_path=("mcp", BINARY),
        leaf={"type": "local", "command": [BINARY, "mcp"], "enabled": True},
        skills_dir=".config/opencode/skills",
        home_marker=".config/opencode",
    ),
}


def wire_skill(c: Client) -> tuple[Status, str]:
    if c.skills_dir is None:
        return Status.SKIPPED, "no skill auto-load"
    home = Path.home()
    marker = home / (c.home_marker or PurePosixPath(c.skills_dir).parts[0])
    if not marker.exists():
        return Status.ABSENT, "host not installed"
    skills_root = home / c.skills_dir
    skills_root.mkdir(parents=True, exist_ok=True)
    link = skills_root / SKILL_NAME
    source = Path(str(resources.files("holo_desktop.host_skills").joinpath(SKILL_NAME)))
    if link.is_symlink():
        # `strict=False`: a fresh-venv pip install can leave a symlink dangling at removed sitepackages.
        if link.resolve(strict=False) == source.resolve(strict=False):
            return Status.SKIPPED, home_short(link)
        link.unlink()
    elif link.exists():
        skill_md = link / "SKILL.md"
        src_md = source / "SKILL.md"
        is_holo_skill_dir = link.is_dir() and skill_md.exists()
        if is_holo_skill_dir and src_md.exists() and skill_md.read_bytes() == src_md.read_bytes():
            return Status.SKIPPED, home_short(link)
        if not is_holo_skill_dir:
            return Status.FAILED, f"{home_short(link)} exists and is not a holo skill"
        shutil.rmtree(link)
    try:
        link.symlink_to(source, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        # Windows without Developer Mode can't symlink; mirror the tree as a fallback.
        if os.name == "nt":
            try:
                if link.exists():
                    shutil.rmtree(link) if link.is_dir() and not link.is_symlink() else link.unlink()
                shutil.copytree(source, link)
                return Status.INSTALLED, f"{home_short(link)} (copy; enable Developer Mode for symlinks)"
            except OSError as copy_exc:
                return Status.FAILED, f"{link}: {copy_exc}"
        return Status.FAILED, f"{link}: {exc}"
    return Status.INSTALLED, home_short(link)


def host_present(c: Client) -> bool:
    if c.present is not None:
        return c.present()
    home = Path.home()
    if c.home_marker and (home / c.home_marker).exists():
        return True
    return bool(c.config_path and Path(c.config_path).expanduser().parent.exists())


def host_target(c: Client) -> str:
    """Where Holo's config lands for this host (~-path, or 'via CLI' for CLI-managed hosts)."""
    if c.target is not None:
        return c.target
    return home_short(c.config_path) if c.config_path else "via CLI"
