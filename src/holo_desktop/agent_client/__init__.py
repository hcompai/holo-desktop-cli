"""Thin client to the hai-agent-runtime binary."""

from holo_desktop.agent_client.client import AgentApiClient, SessionStream
from holo_desktop.agent_client.launcher import (
    AgentDaemon,
    SpawnConfig,
    ensure_running,
    runtime_log_path,
    runtime_log_tail,
)

__all__ = [
    "AgentApiClient",
    "AgentDaemon",
    "SessionStream",
    "SpawnConfig",
    "ensure_running",
    "runtime_log_path",
    "runtime_log_tail",
]
