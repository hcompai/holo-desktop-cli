"""Bridge Holo's spawn-time configuration into the hai-agents local runtime."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from hai_agents.local import LocalRuntime
from pydantic import BaseModel

from holo_desktop.agent_client.model_gateway import PRODUCTION_GATEWAY_URL
from holo_desktop.settings import (
    RUNTIME_BASE_URL_ENV,
    HoloSettings,
    load_holo_settings,
)

logger = logging.getLogger(__name__)

LOOPBACK_HOST = "127.0.0.1"
MODELS_API_BASE_URL_ENV = "HAI_BASE_URL"
SPAWN_TIMEOUT_S = 45.0
# Disabled by default: without a Datadog Agent, ddtrace only adds noise and a shutdown flush hang.
DDTRACE_DEFAULT_OFF: dict[str, str] = {
    "DD_TRACE_ENABLED": "false",
    "DD_LLMOBS_ENABLED": "false",
}


def apply_hosted_gateway_default(env: dict[str, str]) -> None:
    """Default hosted runtime calls to the production gateway unless the caller chose another gateway."""
    if not env.get(MODELS_API_BASE_URL_ENV, "").strip():
        env[MODELS_API_BASE_URL_ENV] = PRODUCTION_GATEWAY_URL


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
    """Agent-API port from ``HAI_AGENT_RUNTIME_PORT``, falling back to the default port."""
    return settings.runtime.port


class SpawnConfig(BaseModel):
    """Spawn-time knobs for the binary; they only reach a freshly spawned process."""

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


def _runtime_flags_env(config: SpawnConfig) -> dict[str, str]:
    """The HAI_AGENT_RUNTIME_* deltas a fresh spawn needs (auth token + port are SDK-owned)."""
    extra: dict[str, str] = {}
    if config.fake:
        extra["HAI_AGENT_RUNTIME_FAKE"] = "1"
    if config.fast:
        extra["HAI_AGENT_RUNTIME_FAST"] = "1"
    if config.model:
        extra["HAI_AGENT_RUNTIME_MODEL"] = config.model
    if config.base_url:
        extra[RUNTIME_BASE_URL_ENV] = config.base_url
    if config.runs_dir:
        # A quoted "~/..." bypasses shell expansion; never hand the binary a literal tilde.
        extra["HAI_AGENT_RUNTIME_RUNS_DIR"] = str(config.runs_dir.expanduser())
    return extra


def _reject_ignored_flags(config: SpawnConfig, base_url: str) -> None:
    """Preserved ensure_running guard: a running runtime keeps the config it was started with."""
    valued = (("--model", config.model), ("--base-url", config.base_url), ("--runs-dir", config.runs_dir))
    requested = [f"{name} {value}" for name, value in valued if value]
    requested += [name for name, on in (("--fake", config.fake), ("--fast", config.fast)) if on]
    if config.require_fresh_for_config and requested:
        flags = " ".join(requested)
        raise RuntimeError(
            f"An agent server is already running at {base_url} and keeps the configuration "
            f"it was started with, so '{flags}' would be silently ignored. "
            "Stop that server, or pass a different --port to spawn a fresh one with your flags."
        )


def ensure_local_runtime(config: SpawnConfig, *, settings: HoloSettings) -> LocalRuntime:
    """Attach to a running runtime on ``config.port`` or spawn one through the SDK.

    inherit_env=False makes spawn_env the complete child environment used verbatim
    (plan 002 contract), so runtime_child_env keeps owning the os.environ merge, the
    ddtrace defaults, the hosted-gateway default, and the self-hosted HAI_API_KEY strip.
    """
    existing = LocalRuntime.attach(port=config.port)
    if existing is not None:
        _reject_ignored_flags(config, existing.base_url)
        return existing
    return LocalRuntime.ensure_started(
        port=config.port,
        spawn_env=runtime_child_env(_runtime_flags_env(config), settings=settings),
        inherit_env=False,
        timeout_s=SPAWN_TIMEOUT_S,
    )


def ensure_local_runtime_from_env() -> LocalRuntime:
    """``ensure_local_runtime`` configured purely from ``HAI_AGENT_RUNTIME_*`` env (stdio servers: mcp/acp)."""
    settings = load_holo_settings()
    return ensure_local_runtime(spawn_config_from_env(settings=settings), settings=settings)
