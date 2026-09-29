"""Spawn, health-check and stop the hai-agent-runtime binary on loopback."""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import signal
import subprocess
from dataclasses import dataclass
from pathlib import Path

import httpx
from hai_agents.local import state as runtime_state
from hai_agents.local.process import log_tail, terminate
from hai_agents.local.runtime import LocalRuntime
from pydantic import BaseModel

from holo_desktop.agent_client import runtime_install
from holo_desktop.agent_client.model_gateway import PRODUCTION_GATEWAY_URL
from holo_desktop.settings import (
    AGENT_API_DEFAULT_PORT as _AGENT_API_DEFAULT_PORT,
)
from holo_desktop.settings import (
    AUTH_TOKEN_ENV as AUTH_TOKEN_ENV,
)
from holo_desktop.settings import (
    PORT_ENV as PORT_ENV,
)
from holo_desktop.settings import (
    RUNTIME_BASE_URL_ENV,
    HoloSettings,
    load_holo_settings,
)

logger = logging.getLogger(__name__)

LOOPBACK_HOST = "127.0.0.1"
MODELS_API_BASE_URL_ENV = "HAI_BASE_URL"
AGENT_API_DEFAULT_PORT = _AGENT_API_DEFAULT_PORT
# Disabled by default: without a Datadog Agent, ddtrace only adds noise and a shutdown flush hang.
DDTRACE_DEFAULT_OFF: dict[str, str] = {
    "DD_TRACE_ENABLED": "false",
    "DD_LLMOBS_ENABLED": "false",
}
# stderr goes to a file, not a pipe: nobody drains a pipe after spawn, so the buffer would fill and block.
LOG_DIR = Path.home() / ".holo" / "logs"
TOKEN_DIR = Path.home() / ".holo"


def apply_hosted_gateway_default(env: dict[str, str]) -> None:
    """Default hosted runtime calls to the production gateway unless the caller chose another gateway."""
    if not env.get(MODELS_API_BASE_URL_ENV, "").strip():
        env[MODELS_API_BASE_URL_ENV] = PRODUCTION_GATEWAY_URL


def token_file_path(port: int) -> Path:
    """Where a spawner publishes its generated bearer token for other local clients."""
    return runtime_state.token_file_path(port, cache_dir=TOKEN_DIR)


def pid_file_path(port: int) -> Path:
    """Where a spawner publishes the runtime pid so ``holo stop --force`` can signal it."""
    return runtime_state.pid_file_path(port, cache_dir=TOKEN_DIR)


def read_pid_file(port: int) -> int | None:
    """The spawned runtime's pid for ``port``, or None when no readable pid file exists."""
    try:
        path = pid_file_path(port)
        if not path.exists():
            path = TOKEN_DIR / f"agent-pid-{port}"
        return int(path.read_text(encoding="utf-8").strip())
    except (FileNotFoundError, ValueError):
        return None
    except OSError as exc:
        logger.warning("could not read pid file %s: %s", pid_file_path(port), exc)
        return None


def discover_runtime_pids(port: int | None) -> list[int]:
    """Pids of live spawned runtimes from pid files: one ``port``, or every spawned runtime when None.

    A runtime that exits uncleanly leaves its pid file behind and the OS may hand the pid to an
    unrelated process, so each pid is checked against its command line before it is returned.
    """
    if port is not None:
        pid = read_pid_file(port)
        return [pid] if pid is not None and process_is_runtime(pid) else []
    pids: list[int] = []
    # Emergency stop must still discover a daemon started by the released CLI.
    paths = [*(TOKEN_DIR / "state").glob("agent-pid-*"), *TOKEN_DIR.glob("agent-pid-*")]
    for path in sorted(paths):
        try:
            pid = int(path.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            continue
        if pid not in pids and process_is_runtime(pid):
            pids.append(pid)
    return pids


def process_is_runtime(pid: int) -> bool:
    """True when ``pid`` is alive and its command line names the runtime binary."""
    if os.name == "posix":
        cmd = ["ps", "-ww", "-o", "command=", "-p", str(pid)]
    else:
        cmd = ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, check=False).stdout
    except OSError:
        return False
    return "hai-agent-runtime" in out or "hai_agent_runtime" in out


def _killpg_posix(pid: int, sig: int) -> bool:
    """Send ``sig`` to ``pid``'s process group; False if the process/group is already gone."""
    try:
        os.killpg(os.getpgid(pid), sig)
    except (OSError, ProcessLookupError):
        return False
    return True


def kill_runtime_by_pid(pid: int) -> bool:
    """Force-kill the runtime's process group by pid; False if it was already gone."""
    if os.name == "posix":
        return _killpg_posix(pid, signal.SIGKILL)
    try:
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], check=True, capture_output=True)
    except (OSError, subprocess.CalledProcessError):
        return False
    return True


def runtime_log_path(port: int) -> Path:
    """Where the runtime spawned on `port` writes its stderr."""
    return LOG_DIR / f"hai-agent-runtime-{port}.log"


def runtime_log_tail(port: int) -> str:
    """Last chunk of the runtime's stderr log for `port`; a placeholder when missing/empty."""
    return log_tail(runtime_log_path(port))


@dataclass
class AgentDaemon:
    """A reachable agent-API server: where it is, how to authenticate, and (if ours) the process."""

    base_url: str
    token: str
    proc: subprocess.Popen[bytes] | None
    # Set only on the spawner that published a generated token; attachers never own the file.
    token_file: Path | None
    # From /health; None when the server does not report one.
    runtime_version: str | None
    # Set only on the spawner; published so `holo stop --force` can find the runtime from another process.
    pid_file: Path | None = None
    runtime: LocalRuntime | None = None
    legacy: bool = False

    async def aclose(self) -> None:
        """Stop the daemon if we spawned it; no-op if we attached to an existing one."""
        if self.runtime is not None:
            if self.runtime.owned:
                await asyncio.to_thread(self.runtime.shutdown)
            return
        if self.proc is not None:
            await _graceful_stop(self.proc)
        if self.token_file is not None:
            self.token_file.unlink(missing_ok=True)
        if self.pid_file is not None:
            self.pid_file.unlink(missing_ok=True)


def runtime_child_env(extra: dict[str, str], *, settings: HoloSettings) -> dict[str, str]:
    """Inherited env for the runtime child, plus `extra`; drops the portal key when a custom inference base URL is set."""
    env = {**DDTRACE_DEFAULT_OFF, **os.environ, **extra}
    runtime_base_url = (extra.get(RUNTIME_BASE_URL_ENV) or settings.runtime.base_url or "").strip()
    # A custom base URL points the runtime at a self-hosted endpoint; the portal HAI_API_KEY must not leak to it.
    if runtime_base_url:
        env[RUNTIME_BASE_URL_ENV] = runtime_base_url
        env.pop("HAI_API_KEY", None)
    else:
        env.pop(RUNTIME_BASE_URL_ENV, None)
        apply_hosted_gateway_default(env)
    return env


def port_from_env(*, settings: HoloSettings) -> int:
    """Agent-API port from ``HAI_AGENT_RUNTIME_PORT``, falling back to :data:`AGENT_API_DEFAULT_PORT`."""
    return settings.runtime.port


class SpawnConfig(BaseModel):
    """Spawn-time knobs for the binary; they only reach a freshly spawned process (see :func:`ensure_running`)."""

    port: int
    model: str | None = None
    base_url: str | None = None
    fake: bool = False
    fast: bool = False
    # None leaves the binary's own default (~/.holo/runs).
    runs_dir: Path | None = None
    # Explicit CLI config must not be silently ignored on attach; env-derived config attaches best-effort.
    require_fresh_for_config: bool = True


def spawn_config_from_env(*, settings: HoloSettings) -> SpawnConfig:
    """:class:`SpawnConfig` purely from ``HAI_AGENT_RUNTIME_*`` env (stdio servers: mcp/acp)."""
    runtime = settings.runtime
    return SpawnConfig(
        port=runtime.port,
        model=runtime.model,
        base_url=runtime.base_url,
        require_fresh_for_config=False,
        fake=runtime.fake,
        fast=runtime.fast,
        # HAI_AGENT_RUNTIME_RUNS_DIR reaches the spawned binary via inherited env.
        runs_dir=None,
    )


async def ensure_running_from_env() -> AgentDaemon:
    """``ensure_running`` configured purely from ``HAI_AGENT_RUNTIME_*`` env (stdio servers: mcp/acp)."""
    settings = load_holo_settings()
    return await ensure_running(spawn_config_from_env(settings=settings), settings=settings)


def resolve_command(*, settings: HoloSettings) -> list[str]:
    """Resolve the runtime command: PATH > managed install > download-on-first-run; raises otherwise."""
    found = shutil.which("hai-agent-runtime")
    if found:
        logger.info("resolved hai-agent-runtime from PATH: %s", found)
        return [found]
    managed = runtime_install.installed_binary(runtime_install.PINNED_RUNTIME_VERSION)
    if managed is not None:
        logger.info(
            "resolved hai-agent-runtime from managed install v%s: %s", runtime_install.PINNED_RUNTIME_VERSION, managed
        )
        return [str(managed)]
    # Resolve before prompting so an unsupported platform fails before the user approves a doomed download.
    artifact = runtime_install.pinned_artifact(settings=settings.install)
    if not runtime_install.confirm_download():
        raise RuntimeError(
            "hai-agent-runtime not found: not on PATH, no managed install under "
            f"{runtime_install.RUNTIME_DIR}, and the download was declined. "
            "Re-run and accept the download, or put hai-agent-runtime on PATH."
        )
    installed = runtime_install.install_runtime(artifact)
    logger.info(
        "resolved hai-agent-runtime from fresh download v%s: %s", runtime_install.PINNED_RUNTIME_VERSION, installed
    )
    return [str(installed)]


@dataclass
class HealthProbe:
    """A 200 from /health; `version` when the body reports one."""

    version: str | None


async def probe_health(base_url: str) -> HealthProbe | None:
    """None when unreachable/unhealthy; otherwise the probe with a best-effort version."""
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.get(f"{base_url}/health")
    except httpx.HTTPError:
        return None
    if response.status_code != 200:
        return None
    try:
        payload = response.json()
    except ValueError:
        return HealthProbe(version=None)
    version = payload.get("version") if isinstance(payload, dict) else None
    return HealthProbe(version=version if isinstance(version, str) else None)


async def ensure_running(config: SpawnConfig, *, settings: HoloSettings) -> AgentDaemon:
    """Use the SDK's authenticated runtime lifecycle, keeping CLI launch policy."""
    server_url = f"http://{LOOPBACK_HOST}:{config.port}"
    probe = await probe_health(server_url)
    valued = (("--model", config.model), ("--base-url", config.base_url), ("--runs-dir", config.runs_dir))
    requested = [f"{name} {value}" for name, value in valued if value]
    requested += [name for name, enabled in (("--fake", config.fake), ("--fast", config.fast)) if enabled]
    if probe is not None and config.require_fresh_for_config and requested:
        raise RuntimeError(
            f"An agent server is already running at {server_url}; explicit launch flags {' '.join(requested)} would be ignored. "
            "Stop it or choose another --port."
        )
    # Keep the released latency preset until its settings have an equivalent shared profile.
    recipe = "desktop" if config.fast else "shared"
    extra = {"HAI_AGENT_RUNTIME_RECIPE": recipe}
    if config.fast:
        extra["HAI_AGENT_RUNTIME_FAST"] = "1"
    if config.fake:
        extra["HAI_AGENT_RUNTIME_FAKE"] = "1"
    if config.model:
        extra["HAI_AGENT_RUNTIME_MODEL"] = config.model
    if config.base_url:
        extra["HAI_AGENT_RUNTIME_BASE_URL"] = config.base_url
    if config.runs_dir:
        extra["HAI_AGENT_RUNTIME_RUNS_DIR"] = str(config.runs_dir.expanduser())
    options = dict(
        port=config.port,
        cache_dir=TOKEN_DIR,
        required_recipe=recipe,
        spawn_env=runtime_child_env(extra, settings=settings),
        inherit_env=False,
    )
    if probe is None:
        if explicit := os.environ.get("HAI_AGENT_LOCAL_BINARY_PATH"):
            options["binary_path"] = explicit
        else:
            options["command"] = await asyncio.to_thread(resolve_command, settings=settings)
    runtime = await LocalRuntime.ensure_started_async(**options)
    return AgentDaemon(
        base_url=runtime.base_url,
        token=runtime.api_key,
        proc=runtime._proc,
        token_file=None,
        runtime_version=runtime.version,
        runtime=runtime,
        legacy=config.fast or config.fake,
    )


# Heuristic markers of macOS TCC failures in the binary's stderr.
PERMISSION_ERROR_HINTS = (
    "accessibility",
    "screen recording",
    "screencapture",
    "could not create image from display",
    "tcc",
    "not permitted",
    "permission",
)


def text_suggests_permissions(text: str) -> bool:
    """True when ``text`` (stderr tail, session error, ...) looks like a macOS permission failure."""
    lowered = text.lower()
    return any(hint in lowered for hint in PERMISSION_ERROR_HINTS)


API_KEY_ERROR_HINTS = ("unauthorized", "invalid api key", "api key is required", "authenticationfailed")


def text_suggests_bad_api_key(text: str) -> bool:
    """True when a session error looks like the model gateway rejecting the bearer token."""
    lowered = text.lower()
    return any(hint in lowered for hint in API_KEY_ERROR_HINTS)


def log_tail_suggests_permissions(port: int) -> bool:
    """True when the runtime's recent stderr looks like a macOS permission failure."""
    path = runtime_log_path(port)
    try:
        data = path.read_bytes()[-8192:]
    except OSError:
        return False
    return text_suggests_permissions(data.decode("utf-8", errors="replace"))



async def _graceful_stop(proc: subprocess.Popen[bytes]) -> None:
    await asyncio.to_thread(terminate, proc)
