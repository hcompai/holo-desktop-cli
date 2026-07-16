"""Thin client to the hai-agent-runtime binary (lifecycle delegated to hai-agents local mode)."""

from holo_desktop.agent_client.client import AgentApiClient, SessionStream
from holo_desktop.agent_client.sdk_runtime import (
    SpawnConfig,
    ensure_local_runtime,
    ensure_local_runtime_from_env,
)

__all__ = [
    "AgentApiClient",
    "SessionStream",
    "SpawnConfig",
    "ensure_local_runtime",
    "ensure_local_runtime_from_env",
]
