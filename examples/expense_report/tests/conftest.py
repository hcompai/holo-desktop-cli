"""Shared test fixtures for the expense-report demo suite.

`fake_agent_server` stands up a minimal agent-API on a free loopback port so
the real `port_from_env` / `require_api_key` / `ensure_running` wiring runs
end-to-end without the `hai-agent-runtime` binary. A dropped `settings=` on any
of those calls then surfaces as a loud `TypeError`.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Iterator
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import urlsplit

import pytest
from hai_agents_local.config import AUTO_BRIDGE_ENV_VAR
from hai_agents_local.runtime.acquire import SHARED_RECIPE
from hai_agents_local.runtime.identity import CHALLENGE_HEADER, PROOF_HEADER
from holo_desktop.settings import AUTH_TOKEN_ENV

FAKE_ANSWER = "demo answer"
FAKE_TOKEN = "test-token"


@pytest.fixture
def fake_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect `Path.home()` to tmp on POSIX (`HOME`) and Windows (`USERPROFILE`)."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    return tmp_path


_COMPLETED_CHANGES = {
    "status": "completed",
    "error": None,
    "new_events": [],
    "answer": FAKE_ANSWER,
}


class _AgentApiHandler(BaseHTTPRequestHandler):
    """Minimal agent-API that proves its identity: healthy, one session, immediately-completed trajectory."""

    def end_headers(self) -> None:
        challenge = self.headers.get(CHALLENGE_HEADER, "")
        self.send_header(PROOF_HEADER, hmac.new(FAKE_TOKEN.encode(), challenge.encode(), hashlib.sha256).hexdigest())
        super().end_headers()

    def _json(self, payload: dict[str, object]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        if path == "/health":
            self._json({"status": "ok", "recipe": SHARED_RECIPE})
        elif path == "/api/v2/sessions":
            self._json({"items": []})
        elif path.endswith("/changes"):
            self._json(_COMPLETED_CHANGES)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self) -> None:
        if self.path.endswith("/sessions"):
            request = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))) or b"{}")
            self._json(
                {
                    "id": "fake-session",
                    "request": request,
                    "status": {"status": "pending"},
                    "created_at": datetime.now(UTC).isoformat(),
                }
            )
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format: str, *args: object) -> None:  # stdlib signature; silences request logs
        return


@pytest.fixture
def fake_agent_server(monkeypatch: pytest.MonkeyPatch) -> Iterator[int]:
    """Yield the loopback port of a running fake agent-API server the client can authenticate against."""
    monkeypatch.setenv(AUTH_TOKEN_ENV, FAKE_TOKEN)
    # The fake drives no device, so sessions must not start local desktop bridges.
    monkeypatch.setenv(AUTO_BRIDGE_ENV_VAR, "0")
    server = ThreadingHTTPServer(("127.0.0.1", 0), _AgentApiHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()
        thread.join(timeout=5.0)
