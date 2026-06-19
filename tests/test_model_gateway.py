"""Behavioural tests for the live model-gateway probe.

Each case runs against a real loopback HTTP server returning a fixed status, so
the probe's classification is exercised end-to-end over httpx, not mocked.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

from holo_desktop.agent_client.model_gateway import (
    PRODUCTION_GATEWAY_URL,
    probe_model_access,
    resolve_gateway_url,
)

_TIMEOUT_S = 5.0


@contextmanager
def _gateway_server(status: int) -> Iterator[str]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            body = b'{"data": []}'
            self.send_response(status)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:  # stdlib signature; silence request logs
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/v1/models"
    finally:
        server.shutdown()
        thread.join(timeout=5.0)


def test_ok_is_entitled() -> None:
    with _gateway_server(200) as url:
        assert probe_model_access(url, "good-key", _TIMEOUT_S) == "entitled"


def test_unauthorized_is_unauthorized() -> None:
    with _gateway_server(401) as url:
        assert probe_model_access(url, "dead-key", _TIMEOUT_S) == "unauthorized"


def test_forbidden_is_unauthorized() -> None:
    with _gateway_server(403) as url:
        assert probe_model_access(url, "scoped-out-key", _TIMEOUT_S) == "unauthorized"


def test_server_error_is_unverifiable_not_a_false_rejection() -> None:
    # A 503 must not be reported as a credential problem; callers must not hard-fail.
    with _gateway_server(503) as url:
        assert probe_model_access(url, "any-key", _TIMEOUT_S) == "unverifiable"


def test_transport_error_is_unverifiable() -> None:
    # Nothing listens on port 1: a connection failure classifies as unverifiable, never unauthorized.
    assert probe_model_access("http://127.0.0.1:1/v1/models", "any-key", _TIMEOUT_S) == "unverifiable"


def test_resolve_defaults_to_production() -> None:
    assert resolve_gateway_url({}) == PRODUCTION_GATEWAY_URL


def test_resolve_honors_hai_base_url_override() -> None:
    assert resolve_gateway_url({"HAI_BASE_URL": "https://eu.example/v1/models"}) == "https://eu.example/v1/models"


def test_resolve_ignores_blank_override() -> None:
    assert resolve_gateway_url({"HAI_BASE_URL": "   "}) == PRODUCTION_GATEWAY_URL
