"""Behavioural test: `holo run` must honour ``HAI_AGENT_RUNTIME_PORT`` like mcp/acp do.

A fake agent-API server (health + create-session + changes + status) listens on
a free port advertised only via ``HAI_AGENT_RUNTIME_PORT``. With no ``--port``
flag, `run` must attach there — not probe the hardcoded default port and spawn
a fresh binary on the wrong loopback port.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest

from holo_desktop.cli.run import run
from holo_desktop.settings import AUTH_TOKEN_ENV, PORT_ENV

FAKE_ANSWER = "42 unread emails"

_COMPLETED_CHANGES = {
    "status": "completed",
    "error": None,
    "new_events": [],
    "answer": FAKE_ANSWER,
}

# A full session envelope: the SDK client parses the create response typed.
_CREATED_SESSION = {
    "id": "fake-session",
    "request": {"agent": "holo"},
    "status": {"status": "running"},
    "created_at": "2026-06-30T00:00:00Z",
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
        elif self.path.endswith("/status"):
            self._json({"status": "completed", "error": None})
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self) -> None:
        if self.path.endswith("/sessions"):
            self._json(_CREATED_SESSION)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format: str, *args: object) -> None:  # stdlib signature; silences request logs
        return


@contextmanager
def _fake_agent_server() -> Iterator[int]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _AgentApiHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()
        thread.join(timeout=5.0)


@pytest.mark.timeout(60)
def test_run_attaches_to_port_from_env(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv(AUTH_TOKEN_ENV, "test-token")
    monkeypatch.setenv("HAI_API_KEY", "test-key")  # bypass the interactive login bootstrap
    # Crash-only guard: if `run` ignores the env port it tries to spawn on the
    # default port; pointing the SDK's binary override at a missing file makes
    # that die loudly — never fall through to a real binary on PATH.
    monkeypatch.setenv("HAI_AGENT_LOCAL_BINARY_PATH", "/nonexistent/spawn-attempted")

    with _fake_agent_server() as port:
        monkeypatch.setenv(PORT_ENV, str(port))
        run(task="how many unread emails?", quiet=True)

    assert FAKE_ANSWER in capsys.readouterr().out
