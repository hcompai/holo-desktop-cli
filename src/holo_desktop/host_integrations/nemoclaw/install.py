"""Install HoloDesktop into a NemoClaw sandbox."""

from __future__ import annotations

import base64
import contextlib
import json
import os
import secrets
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from importlib import resources
from pathlib import Path
from typing import Any

from holo_desktop.cli.hosts import BINARY, Status, home_short
from holo_desktop.fs import atomic_write_text
from holo_desktop.host_integrations.nemoclaw.constants import (
    BRIDGE_BIND_HOST,
    BRIDGE_HOST,
    BRIDGE_LOG_FILE,
    BRIDGE_PORT,
    BRIDGE_TOKEN_FILE,
    BRIDGE_URL,
    MCP_PROXY_PATH,
    NEMOCLAW_DIR,
)

SKILL_NAME = "holo-desktop"
NEMOCLAW_BINARY = "nemoclaw"
NEMOCLAW_SANDBOX_ENV = "HOLO_NEMOCLAW_SANDBOX"
NEMOCLAW_BRIDGE_PORT = BRIDGE_PORT
NEMOCLAW_BRIDGE_HOST = BRIDGE_HOST
NEMOCLAW_BRIDGE_TOKEN_FILE = BRIDGE_TOKEN_FILE
NEMOCLAW_BRIDGE_LOG_FILE = BRIDGE_LOG_FILE
NEMOCLAW_MCP_PROXY_PATH = MCP_PROXY_PATH
SANDBOX_PROXY_ENV_NAMES = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "NO_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
    "no_proxy",
    "NODE_OPTIONS",
)


def nemoclaw_present() -> bool:
    """True when NemoClaw's CLI and default sandbox are available to wire."""
    exe = shutil.which(NEMOCLAW_BINARY)
    return exe is not None and _default_nemoclaw_sandbox(exe) is not None


def wire_nemoclaw() -> tuple[Status, str]:
    """Install Holo into the default NemoClaw sandbox."""
    exe = shutil.which(NEMOCLAW_BINARY)
    if exe is None:
        return Status.ABSENT, "'nemoclaw' not on PATH; install/onboard NemoClaw first"

    sandbox = os.environ.get(NEMOCLAW_SANDBOX_ENV, "").strip() or _default_nemoclaw_sandbox(exe)
    if not sandbox:
        return (
            Status.FAILED,
            f"no default NemoClaw sandbox found; run `{NEMOCLAW_BINARY} onboard` or set {NEMOCLAW_SANDBOX_ENV}",
        )

    token = _ensure_nemoclaw_bridge_token()
    parts = [f"sandbox {sandbox}"]
    steps = [
        lambda: _ensure_nemoclaw_bridge(token),
        lambda: _apply_nemoclaw_bridge_policy(exe, sandbox),
        lambda: _install_nemoclaw_skill(exe, sandbox),
        lambda: _install_nemoclaw_mcp_deps(exe, sandbox),
        lambda: _upload_nemoclaw_mcp_proxy(exe, sandbox),
        lambda: _set_nemoclaw_mcp(exe, sandbox, token),
    ]
    for step in steps:
        status, detail = step()
        if status.fatal:
            return status, detail
        parts.append(detail)

    recover_status, recover_detail = _recover_nemoclaw_gateway(exe, sandbox)
    if recover_status.ok:
        parts.append(recover_detail)
    else:
        parts.append(f"{recover_detail}; restart NemoClaw if tools do not appear")
    return Status.INSTALLED, "; ".join(parts)


def _default_nemoclaw_sandbox(exe: str) -> str | None:
    completed = _run_host_command([exe, "list", "--json"], timeout=30)
    if completed.returncode != 0:
        return None
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    default = payload.get("defaultSandbox") or payload.get("lastOnboardedSandbox")
    if isinstance(default, str) and default:
        return default
    sandboxes = payload.get("sandboxes")
    if isinstance(sandboxes, list):
        names = [sandbox.get("name") for sandbox in sandboxes if isinstance(sandbox, dict)]
        names = [name for name in names if isinstance(name, str) and name]
        if len(names) == 1:
            return names[0]
    return None


def _ensure_nemoclaw_bridge_token() -> str:
    token_path = _nemoclaw_bridge_token_path()
    if token_path.exists():
        return token_path.read_text(encoding="utf-8").strip()
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token = secrets.token_urlsafe(32)
    atomic_write_text(token_path, token + "\n")
    with contextlib.suppress(OSError):
        os.chmod(token_path, 0o600)
    return token


def _ensure_nemoclaw_bridge(token: str) -> tuple[Status, str]:
    if _nemoclaw_bridge_healthy(token):
        return Status.SKIPPED, f"bridge already running on {NEMOCLAW_BRIDGE_PORT}"
    if conflict := _nemoclaw_bridge_port_conflict():
        return Status.FAILED, conflict

    log_path = _nemoclaw_bridge_log_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_file = log_path.open("ab")
    kwargs: dict[str, Any] = {"stdout": subprocess.DEVNULL, "stderr": log_file}
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen(
        [
            sys.executable,
            "-m",
            "holo_desktop.host_integrations.nemoclaw.bridge_server",
            "--host",
            BRIDGE_BIND_HOST,
            "--port",
            str(NEMOCLAW_BRIDGE_PORT),
            "--token-file",
            str(_nemoclaw_bridge_token_path()),
        ],
        **kwargs,
    )
    log_file.close()
    for _ in range(20):
        if _nemoclaw_bridge_healthy(token):
            return Status.INSTALLED, f"bridge started on {BRIDGE_BIND_HOST}:{NEMOCLAW_BRIDGE_PORT}"
        time.sleep(0.25)
    return Status.FAILED, f"bridge did not become healthy; see {home_short(log_path)}"


def _apply_nemoclaw_bridge_policy(exe: str, sandbox: str) -> tuple[Status, str]:
    policy_path = _nemoclaw_policy_path()
    policy_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(policy_path, _nemoclaw_policy_text())
    completed = _run_host_command(
        [exe, "sandbox", "policy", "add", sandbox, "--from-file", str(policy_path), "--yes"],
        timeout=120,
    )
    if completed.returncode != 0:
        return Status.FAILED, _command_message(completed, "failed to apply NemoClaw bridge policy")
    return Status.INSTALLED, "bridge policy applied"


def _install_nemoclaw_skill(exe: str, sandbox: str) -> tuple[Status, str]:
    source = Path(str(resources.files("holo_desktop.host_skills").joinpath(SKILL_NAME)))
    completed = _run_host_command([exe, "sandbox", "skill", "install", sandbox, str(source)], timeout=120)
    if completed.returncode != 0:
        return Status.FAILED, _command_message(completed, "failed to install Holo skill into NemoClaw")
    return Status.INSTALLED, "skill installed"


def _install_nemoclaw_mcp_deps(exe: str, sandbox: str) -> tuple[Status, str]:
    completed = _run_host_command(
        [
            exe,
            "sandbox",
            "exec",
            sandbox,
            "--timeout",
            "180",
            "--",
            "npm",
            "install",
            "--silent",
            "--prefix",
            "/sandbox",
            "@modelcontextprotocol/sdk",
            "zod",
        ],
        timeout=210,
    )
    if completed.returncode != 0:
        return Status.FAILED, _command_message(completed, "failed to install NemoClaw MCP dependencies")
    return Status.INSTALLED, "MCP deps installed"


def _upload_nemoclaw_mcp_proxy(exe: str, sandbox: str) -> tuple[Status, str]:
    source = resources.files("holo_desktop.host_integrations.nemoclaw").joinpath("holo_mcp_bridge.mjs")
    encoded = base64.b64encode(source.read_bytes()).decode("ascii")
    script = (
        f"import base64, pathlib; pathlib.Path({NEMOCLAW_MCP_PROXY_PATH!r}).write_bytes(base64.b64decode({encoded!r}))"
    )
    completed = _run_host_command(
        [exe, "sandbox", "exec", sandbox, "--timeout", "30", "--", "python3", "-c", script],
        timeout=60,
    )
    if completed.returncode != 0:
        return Status.FAILED, _command_message(completed, "failed to upload Holo MCP proxy")
    return Status.INSTALLED, "MCP proxy uploaded"


def _set_nemoclaw_mcp(exe: str, sandbox: str, token: str) -> tuple[Status, str]:
    mcp_env = {
        **_sandbox_proxy_env(exe, sandbox),
        "HOLO_BRIDGE_URL": BRIDGE_URL,
        "HOLO_BRIDGE_PORT": str(NEMOCLAW_BRIDGE_PORT),
        "HOLO_BRIDGE_TOKEN": token,
        "NODE_USE_ENV_PROXY": "1",
        # NemoClaw sandboxes can use either system Node or Linuxbrew Node depending on image/onboarding.
        "PATH": "/usr/local/bin:/usr/bin:/bin:/home/linuxbrew/.linuxbrew/bin",
    }
    mcp_config = {
        "command": "node",
        "args": [NEMOCLAW_MCP_PROXY_PATH],
        "env": mcp_env,
    }
    completed = _run_host_command(
        [
            exe,
            "sandbox",
            "exec",
            sandbox,
            "--timeout",
            "30",
            "--",
            "openclaw",
            "mcp",
            "set",
            BINARY,
            json.dumps(mcp_config),
        ],
        timeout=60,
    )
    if completed.returncode != 0:
        return Status.FAILED, _sanitize(_command_message(completed, "failed to register Holo MCP in NemoClaw"), token)
    return Status.INSTALLED, "MCP registered"


def _sandbox_proxy_env(exe: str, sandbox: str) -> dict[str, str]:
    script = (
        "import json, os; "
        f"keys = {json.dumps(list(SANDBOX_PROXY_ENV_NAMES))}; "
        "print(json.dumps({key: os.environ[key] for key in keys if os.environ.get(key)}))"
    )
    completed = _run_host_command(
        [exe, "sandbox", "exec", sandbox, "--timeout", "30", "--", "python3", "-c", script],
        timeout=60,
    )
    if completed.returncode != 0:
        return {}
    try:
        loaded = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return {}
    if not isinstance(loaded, dict):
        return {}
    return {key: value for key, value in loaded.items() if key in SANDBOX_PROXY_ENV_NAMES and isinstance(value, str)}


def _recover_nemoclaw_gateway(exe: str, sandbox: str) -> tuple[Status, str]:
    completed = _run_host_command([exe, "sandbox", "recover", sandbox], timeout=120)
    if completed.returncode != 0:
        return Status.FAILED, _command_message(completed, "gateway recover failed")
    return Status.INSTALLED, "gateway restarted"


def _nemoclaw_bridge_healthy(token: str) -> bool:
    request = urllib.request.Request(
        f"http://127.0.0.1:{NEMOCLAW_BRIDGE_PORT}/health",
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=1) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return False
    return (
        response.status == 200
        and isinstance(payload, dict)
        and payload.get("name") == "holo-nemoclaw-bridge"
        and payload.get("auth") is True
    )


def _nemoclaw_bridge_port_conflict() -> str | None:
    request = urllib.request.Request(f"http://127.0.0.1:{NEMOCLAW_BRIDGE_PORT}/health")
    try:
        with urllib.request.urlopen(request, timeout=1) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            return (
                f"port {NEMOCLAW_BRIDGE_PORT} is already running the Holo NemoClaw bridge, "
                "but the saved token did not authorize; stop the existing bridge and retry"
            )
        return f"port {NEMOCLAW_BRIDGE_PORT} is already in use and returned HTTP {exc.code}"
    except (OSError, urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None
    if response.status == 200 and isinstance(payload, dict) and payload.get("name") == "holo-nemoclaw-bridge":
        return (
            f"port {NEMOCLAW_BRIDGE_PORT} is already running the Holo NemoClaw bridge, "
            "but the saved token did not authorize; stop the existing bridge and retry"
        )
    return f"port {NEMOCLAW_BRIDGE_PORT} is already in use by something other than the Holo NemoClaw bridge"


def _nemoclaw_policy_text() -> str:
    return f"""preset:
  name: holo-host-bridge
network_policies:
  holo-host-bridge:
    name: holo-host-bridge
    endpoints:
      - host: {NEMOCLAW_BRIDGE_HOST}
        port: {NEMOCLAW_BRIDGE_PORT}
        protocol: rest
        enforcement: enforce
        allowed_ips:
          - 10.0.0.0/8
          - 172.16.0.0/12
          - 192.168.0.0/16
          - fc00::/7
        rules:
          - allow:
              method: GET
              path: /health
          - allow:
              method: POST
              path: /launch
          - allow:
              method: POST
              path: /poll
          - allow:
              method: POST
              path: /kill
    binaries:
      - path: /usr/local/bin/node
      - path: /home/linuxbrew/.linuxbrew/bin/node
      - path: /usr/bin/node
      - path: /usr/bin/curl
"""


def _run_host_command(cmd: list[str], *, timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=timeout)


def _command_message(completed: subprocess.CompletedProcess[str], fallback: str) -> str:
    return (completed.stderr or completed.stdout or fallback).strip() or fallback


def _sanitize(text: str, secret: str) -> str:
    return text.replace(secret, "[redacted]") if secret else text


def _nemoclaw_dir() -> Path:
    return NEMOCLAW_DIR


def _nemoclaw_bridge_token_path() -> Path:
    return _nemoclaw_dir() / NEMOCLAW_BRIDGE_TOKEN_FILE


def _nemoclaw_bridge_log_path() -> Path:
    return _nemoclaw_dir() / NEMOCLAW_BRIDGE_LOG_FILE


def _nemoclaw_policy_path() -> Path:
    return _nemoclaw_dir() / "holo-host-bridge-policy.yaml"
