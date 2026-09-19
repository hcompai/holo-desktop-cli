"""Spawn, health-check and stop the hai-agent-runtime binary on loopback."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import secrets
import shutil
import signal
import subprocess
from dataclasses import dataclass
from pathlib import Path

import httpx
from pydantic import BaseModel

from holo_desktop.agent_client import runtime_install
from holo_desktop.agent_client.model_gateway import PRODUCTION_GATEWAY_URL
from holo_desktop.settings import (
    AGENT_API_DEFAULT_PORT as _AGENT_API_DEFAULT_PORT,
)
from holo_desktop.settings import (
    AUTH_TOKEN_ENV,
    PORT_ENV,
    RUNTIME_BASE_URL_ENV,
    HoloSettings,
    load_holo_settings,
)

logger = logging.getLogger(__name__)

LOOPBACK_HOST = "127.0.0.1"
MODELS_API_BASE_URL_ENV = "HAI_BASE_URL"
AGENT_API_DEFAULT_PORT = _AGENT_API_DEFAULT_PORT
SPAWN_TIMEOUT_S = 45.0
# Disabled by default: without a Datadog Agent, ddtrace only adds noise and a shutdown flush hang.
DDTRACE_DEFAULT_OFF: dict[str, str] = {
    "DD_TRACE_ENABLED": "false",
    "DD_LLMOBS_ENABLED": "false",
}
# stderr goes to a file, not a pipe: nobody drains a pipe after spawn, so the buffer would fill and block.
LOG_DIR = Path.home() / ".holo" / "logs"
LOG_TAIL_CHARS = 4000
TOKEN_DIR = Path.home() / ".holo"


def apply_hosted_gateway_default(env: dict[str, str]) -> None:
    """Default hosted runtime calls to the production gateway unless the caller chose another gateway."""
    if not env.get(MODELS_API_BASE_URL_ENV, "").strip():
        env[MODELS_API_BASE_URL_ENV] = PRODUCTION_GATEWAY_URL


def token_file_path(port: int) -> Path:
    """Where a spawner publishes its generated bearer token for other local clients."""
    return TOKEN_DIR / f"agent-token-{port}"


def pid_file_path(port: int) -> Path:
    """Where a spawner publishes the runtime pid so ``holo stop --force`` can signal it."""
    return TOKEN_DIR / f"agent-pid-{port}"


def read_pid_file(port: int) -> int | None:
    """The spawned runtime's pid for ``port``, or None when no readable pid file exists."""
    try:
        return int(pid_file_path(port).read_text(encoding="utf-8").strip())
    except (FileNotFoundError, ValueError):
        return None
    except OSError as exc:
        logger.warning("could not read pid file %s: %s", pid_file_path(port), exc)
        return None


def discover_runtime_pids(port: int | None) -> list[int]:
    """Pids of spawned runtimes from pid files: one ``port``, or every spawned runtime when None.

    Gotcha: a runtime that exits uncleanly (crash/SIGKILL) leaves its pid file behind, so a later
    ``holo stop --force`` can SIGKILL a recycled pid. There is no proof-of-identity check yet; the
    robust fix (match the process start time) is tracked as follow-up.
    """
    if port is not None:
        pid = read_pid_file(port)
        return [pid] if pid is not None else []
    pids: list[int] = []
    for path in sorted(TOKEN_DIR.glob("agent-pid-*")):
        try:
            pids.append(int(path.read_text(encoding="utf-8").strip()))
        except (OSError, ValueError):
            continue
    return pids


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
    return _log_tail(runtime_log_path(port))


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

    async def aclose(self) -> None:
        """Stop the daemon if we spawned it; no-op if we attached to an existing one."""
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


def _check_runtime_version(version: str | None) -> None:
    """Warn (not fail) on a client/runtime version skew; PATH/override dev binaries stay usable."""
    if version is not None and version != runtime_install.PINNED_RUNTIME_VERSION:
        logger.warning(
            "hai-agent-runtime version skew: server reports %s, this client pins %s; "
            "wire-contract drift may cause subtle failures",
            version,
            runtime_install.PINNED_RUNTIME_VERSION,
        )


async def ensure_running(config: SpawnConfig, *, settings: HoloSettings) -> AgentDaemon:
    """Return a reachable :class:`AgentDaemon`, attaching to or spawning the binary."""
    server_url = f"http://{LOOPBACK_HOST}:{config.port}"
    env_token = settings.runtime.api_token or ""

    probe = await probe_health(server_url)
    if probe is not None:
        valued = (("--model", config.model), ("--base-url", config.base_url), ("--runs-dir", config.runs_dir))
        requested = [f"{name} {value}" for name, value in valued if value]
        requested += [name for name, on in (("--fake", config.fake), ("--fast", config.fast)) if on]
        if config.require_fresh_for_config and requested:
            flags = " ".join(requested)
            raise RuntimeError(
                f"An agent server is already running at {server_url} and keeps the configuration "
                f"it was started with, so '{flags}' would be silently ignored. "
                "Stop that server, or pass a different --port to spawn a fresh one with your flags."
            )
        token = env_token or _read_token_file(config.port)
        if not token:
            raise RuntimeError(
                f"An agent server is already running at {server_url} but no credentials were found: "
                f"{AUTH_TOKEN_ENV} is not set and {token_file_path(config.port)} does not exist, "
                "so this client cannot authenticate. Export the token or stop that server."
            )
        _check_runtime_version(probe.version)
        return AgentDaemon(
            base_url=server_url, token=token, proc=None, token_file=None, runtime_version=probe.version, pid_file=None
        )

    token = env_token or secrets.token_urlsafe(32)
    # Publish generated tokens before health so a client racing our /health probe can authenticate;
    # env tokens never touch disk.
    token_file = None if env_token else _write_owner_only(token_file_path(config.port), token)
    try:
        proc, runtime_version = await _spawn(config=config, token=token, settings=settings)
    except BaseException:
        if token_file is not None:
            _unlink_token_if_ours(token_file, token)
        raise
    _check_runtime_version(runtime_version)
    return AgentDaemon(
        base_url=server_url,
        token=token,
        proc=proc,
        token_file=token_file,
        runtime_version=runtime_version,
        pid_file=_write_pid_file(config.port, proc.pid),
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


def log_tail_suggests_permissions(port: int) -> bool:
    """True when the runtime's recent stderr looks like a macOS permission failure."""
    path = runtime_log_path(port)
    try:
        data = path.read_bytes()[-8192:]
    except OSError:
        return False
    return text_suggests_permissions(data.decode("utf-8", errors="replace"))


def _read_token_file(port: int) -> str:
    try:
        return token_file_path(port).read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return ""
    except OSError as exc:
        logger.warning("could not read token file %s: %s", token_file_path(port), exc)
        return ""


def _write_owner_only(path: Path, content: str) -> Path:
    """Write `content` to `path` owner-only, refusing a pre-existing symlink at the path.

    For files whose contents drive a privileged action — the bearer token, and the runtime pid that
    `holo stop --force` SIGKILLs: O_NOFOLLOW refuses a planted symlink and 0o600 keeps them owner-only
    from the first byte, so neither can be steered into authenticating or killing the wrong target.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with contextlib.suppress(OSError):
        path.parent.chmod(0o700)  # owner-only ~/.holo; no-op on Windows
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        if os.name == "posix":
            os.fchmod(fd, 0o600)  # enforce owner-only even if the file pre-existed
        fh.write(content)
    return path


def _write_pid_file(port: int, pid: int) -> Path | None:
    """Best-effort publish of the runtime pid; None when it could not be written."""
    try:
        return _write_owner_only(pid_file_path(port), str(pid))
    except OSError as exc:
        logger.warning("could not write pid file %s: %s", pid_file_path(port), exc)
        return None


def _unlink_token_if_ours(path: Path, token: str) -> None:
    """Remove our token file, but never one a concurrent spawner already overwrote with its own token."""
    try:
        if path.read_text(encoding="utf-8").strip() == token:
            path.unlink(missing_ok=True)
    except OSError:
        pass


async def _spawn(
    *, config: SpawnConfig, token: str, settings: HoloSettings
) -> tuple[subprocess.Popen[bytes], str | None]:
    """Spawn the binary and wait for health; returns the process and its reported version."""
    server_url = f"http://{LOOPBACK_HOST}:{config.port}"
    extra = {AUTH_TOKEN_ENV: token, PORT_ENV: str(config.port)}
    if config.fake:
        extra["HAI_AGENT_RUNTIME_FAKE"] = "1"
    if config.fast:
        extra["HAI_AGENT_RUNTIME_FAST"] = "1"
    if config.model:
        extra["HAI_AGENT_RUNTIME_MODEL"] = config.model
    if config.base_url:
        extra["HAI_AGENT_RUNTIME_BASE_URL"] = config.base_url
    if config.runs_dir:
        # A quoted "~/..." bypasses shell expansion; never hand the binary a literal tilde.
        extra["HAI_AGENT_RUNTIME_RUNS_DIR"] = str(config.runs_dir.expanduser())
    env = runtime_child_env(extra, settings=settings)

    # resolve_command may download the runtime on first run; keep that off the event loop.
    cmd = await asyncio.to_thread(resolve_command, settings=settings)
    log_path = runtime_log_path(config.port)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger.info("spawning agent binary: %s (stderr -> %s)", " ".join(cmd), log_path)
    # Own process group so we can reap grandchildren (e.g. desktop helpers) the binary may spawn:
    # POSIX gets its own session; Windows a new process group. Each kwarg is a no-op on the other OS.
    with log_path.open("wb") as log_file:  # child inherits the fd; the parent handle can close right away
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=log_file,
            env=env,
            start_new_session=os.name == "posix",
            creationflags=0 if os.name == "posix" else getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
        )

    loop = asyncio.get_running_loop()
    deadline = loop.time() + SPAWN_TIMEOUT_S
    try:
        while True:
            probe = await probe_health(server_url)
            if probe is not None:
                logger.info("agent binary ready (pid %d)", proc.pid)
                return proc, probe.version
            if proc.poll() is not None:
                raise RuntimeError(
                    f"hai-agent-runtime exited with code {proc.returncode}: {_log_tail(log_path)} (full log: {log_path})"
                )
            if loop.time() >= deadline:
                raise RuntimeError(
                    f"hai-agent-runtime did not become healthy within {SPAWN_TIMEOUT_S:.0f}s (see {log_path})"
                )
            await asyncio.sleep(0.25)
    except BaseException:
        # Covers CancelledError too (Ctrl+C mid-spawn): never leak the child we just started.
        _terminate(proc)
        raise


def _log_tail(path: Path) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return "(stderr log unreadable)"
    if not text:
        return "(no stderr output)"
    return text[-LOG_TAIL_CHARS:]


def _signal_runtime(proc: subprocess.Popen[bytes], *, force: bool) -> bool:
    """Signal the runtime's whole process group (posix) or just the process; False if already gone."""
    if os.name == "posix":
        return _killpg_posix(proc.pid, signal.SIGKILL if force else signal.SIGTERM)
    try:
        if force:
            proc.kill()
        else:
            proc.terminate()
    except (OSError, ProcessLookupError):
        return False
    return True


def _terminate(proc: subprocess.Popen[bytes]) -> None:
    if not _signal_runtime(proc, force=False):
        return
    try:
        proc.wait(timeout=2.0)
        return
    except subprocess.TimeoutExpired:
        pass
    if _signal_runtime(proc, force=True):
        try:
            proc.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            logger.warning("hai-agent-runtime (pid %d) did not exit after forced kill", proc.pid)


async def _graceful_stop(proc: subprocess.Popen[bytes]) -> None:
    if proc.poll() is not None:
        return
    await asyncio.to_thread(_terminate, proc)
