"""Shared test fixtures for the expense-report demo suite.

`fake_agent_server` stands up a minimal agent-API on a free loopback port so
the real `port_from_env` / `require_api_key` / `ensure_running` wiring runs
end-to-end without the `hai-agent-runtime` binary. A dropped `settings=` on any
of those calls then surfaces as a loud `TypeError`.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import pytest

FAKE_ANSWER = "demo answer"


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
    """Minimal agent-API: healthy, one session, immediately-completed trajectory."""

    def _json(self, payload: dict[str, object]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/health":
            self.send_response(200)
            self.end_headers()
        elif "/changes" in self.path:
            self._json(_COMPLETED_CHANGES)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self) -> None:
        if self.path.endswith("/sessions"):
            self._json({"id": "fake-session"})
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format: str, *args: object) -> None:  # stdlib signature; silences request logs
        return


@pytest.fixture
def fake_agent_server() -> Iterator[int]:
    """Yield the loopback port of a running fake agent-API server."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), _AgentApiHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()
        thread.join(timeout=5.0)
