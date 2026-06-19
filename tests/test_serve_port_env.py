"""Behavioural test: `holo serve`'s executor must honour ``HAI_AGENT_RUNTIME_PORT``.

Same contract as mcp/acp/run: a healthy agent-API server advertised only via
``HAI_AGENT_RUNTIME_PORT`` must be attached to, not shadowed by a fresh spawn on
the hardcoded default port.
"""

from __future__ import annotations

import asyncio
import importlib
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest

from holo_desktop.agent_client import launcher
from holo_desktop.agent_client.launcher import AUTH_TOKEN_ENV, PORT_ENV
from holo_desktop.cli.serve import HoloExecutor
from holo_desktop.settings import load_holo_settings

serve_mod = importlib.import_module("holo_desktop.cli.serve")


class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.send_response(200 if self.path == "/health" else 404)
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:  # stdlib signature; silences request logs
        return


@contextmanager
def _fake_agent_server() -> Iterator[int]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _HealthHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()
        thread.join(timeout=5.0)


@pytest.mark.timeout(60)
def test_executor_attaches_to_port_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(AUTH_TOKEN_ENV, "test-token")
    # Crash-only stub: a wrong-port spawn attempt must die loudly, never reach a real binary.
    monkeypatch.setattr(launcher, "resolve_command", lambda **_: [sys.executable, "-c", "raise SystemExit(2)"])

    async def startup_and_shutdown(executor: HoloExecutor) -> str:
        await executor.startup()
        assert executor._daemon is not None
        base_url = executor._daemon.base_url
        await executor.shutdown()
        return base_url

    with _fake_agent_server() as port:
        monkeypatch.setenv(PORT_ENV, str(port))
        executor = HoloExecutor(model=None, base_url=None, fake=False, settings=load_holo_settings())
        base_url = asyncio.run(startup_and_shutdown(executor))

    assert base_url == f"http://127.0.0.1:{port}"


def test_blank_holo_auth_token_is_rejected(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("HAI_API_KEY", "key")
    monkeypatch.setenv("HOLO_AUTH_TOKEN", " ")
    monkeypatch.setattr(serve_mod, "build_app", lambda *args, **kwargs: object())

    with pytest.raises(SystemExit) as excinfo:
        serve_mod.serve(port=0)

    assert excinfo.value.code == 1
    assert "HOLO_AUTH_TOKEN is set but empty" in capsys.readouterr().err
