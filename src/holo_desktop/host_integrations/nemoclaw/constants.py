"""Shared NemoClaw integration constants."""

from __future__ import annotations

from holo_desktop.customization import HOLO_DIR

BRIDGE_BIND_HOST = "127.0.0.1"
BRIDGE_HOST = "host.openshell.internal"
BRIDGE_PORT = 19131
BRIDGE_URL = f"http://{BRIDGE_HOST}:{BRIDGE_PORT}"
BRIDGE_TOKEN_FILE = "bridge-token"
BRIDGE_LOG_FILE = "bridge.log"
MCP_PROXY_PATH = "/sandbox/holo-mcp-bridge.mjs"
NEMOCLAW_DIR = HOLO_DIR / "nemoclaw"
