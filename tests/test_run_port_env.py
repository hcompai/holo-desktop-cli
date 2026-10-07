"""Behavioural test: `holo run` must honour ``HAI_AGENT_RUNTIME_PORT`` like mcp does.

A fake agent-API server (health + create-session + changes) listens on a free
port advertised only via ``HAI_AGENT_RUNTIME_PORT``. With no ``--port`` flag,
`run` must attach there — not probe the hardcoded default port and spawn a
fresh binary on the wrong loopback port.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import ThreadingHTTPServer
from threading import Thread

import pytest

from holo_desktop.agent_client import launcher
from holo_desktop.cli.run import run
from holo_desktop.settings import AUTH_TOKEN_ENV, PORT_ENV

from ._runtime_stub import ProvingHandler

FAKE_ANSWER = "42 unread emails"

_COMPLETED_CHANGES = {
    "status": "completed",
    "error": None,
    "new_events": [],
    "answer": FAKE_ANSWER,
}


class _AgentApiHandler(ProvingHandler):
    """Minimal agent-API: healthy, one session, immediately-terminal trajectory."""

    token = "test-token"
    protocol_version = "HTTP/1.1"
    changes: dict[str, object] = _COMPLETED_CHANGES

    def _json(self, payload: dict[str, object]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _empty(self, status: int) -> None:
        self.send_response(status)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self) -> None:
        if self.path == "/health":
            self._json({"status": "ok", "recipe": "shared"})
        elif self.path.startswith("/api/v2/sessions?"):
            self._json({"items": [], "total": 0})
        elif "/changes" in self.path:
            self._json(self.changes)
        else:
            self._empty(404)

    def do_POST(self) -> None:
        request = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0") or "0")) or b"{}")
        if self.path.endswith("/sessions"):
            self._json(
                {
                    "id": "fake-session",
                    "request": request,
                    "status": {"status": "pending"},
                    "created_at": "2026-09-29T12:00:00Z",
                }
            )
        else:
            self._empty(404)


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
    monkeypatch.setenv("HAI_AUTO_BRIDGE", "0")
    monkeypatch.setenv("HAI_API_KEY", "test-key")  # bypass the interactive login bootstrap
    # Crash-only stub: if `run` ignores the env port it tries to spawn on the
    # default port and must die loudly — never fall through to a real binary on PATH.
    monkeypatch.setattr(launcher, "resolve_command", lambda **_: [sys.executable, "-c", "raise SystemExit(2)"])

    with _fake_agent_server() as port:
        monkeypatch.setenv(PORT_ENV, str(port))
        run(task="how many unread emails?", quiet=True)

    assert FAKE_ANSWER in capsys.readouterr().out


@pytest.mark.timeout(60)
def test_run_points_at_login_when_the_gateway_rejects_the_key(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv(AUTH_TOKEN_ENV, "test-token")
    monkeypatch.setenv("HAI_AUTO_BRIDGE", "0")
    monkeypatch.setenv("HAI_API_KEY", "stale-key")
    monkeypatch.setattr(launcher, "resolve_command", lambda **_: [sys.executable, "-c", "raise SystemExit(2)"])
    monkeypatch.setattr(
        _AgentApiHandler,
        "changes",
        {
            "status": "failed",
            "error": "AuthenticationFailedError: Error occurred during vLLM call: Unauthorized",
            "new_events": [],
            "answer": None,
        },
    )

    with _fake_agent_server() as port:
        monkeypatch.setenv(PORT_ENV, str(port))
        with pytest.raises(SystemExit, match="1"):
            run(task="how many unread emails?", quiet=True)

    assert "holo login --force" in capsys.readouterr().err
