"""Behavioural tests for the attach path of ``agent_client.launcher.ensure_running``.

A real loopback HTTP server impersonates an already-running hai-agent-runtime
binary (200 on ``/health``). The launcher must attach when no inference flags
are given, and fail fast — not silently drop the flags — when they are.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import pytest

from holo_desktop.agent_client import launcher
from holo_desktop.agent_client.launcher import AUTH_TOKEN_ENV, SpawnConfig, ensure_running
from holo_desktop.agent_client.runtime_install import PINNED_RUNTIME_VERSION


class _HealthHandler(BaseHTTPRequestHandler):
    health_body: bytes = b""

    def do_GET(self) -> None:
        if self.path != "/health":
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Length", str(len(self.health_body)))
        self.end_headers()
        self.wfile.write(self.health_body)

    def log_message(self, format: str, *args: object) -> None:  # stdlib signature; silences request logs
        return


@contextmanager
def _fake_agent_server(*, health_body: bytes = b"") -> Iterator[int]:
    handler = type("Handler", (_HealthHandler,), {"health_body": health_body})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()
        thread.join(timeout=5.0)


async def _ensure_running(config: SpawnConfig) -> launcher.AgentDaemon:
    return await ensure_running(config, settings=launcher.load_holo_settings())


def test_attach_without_flags_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(AUTH_TOKEN_ENV, "test-token")
    with _fake_agent_server() as port:
        daemon = asyncio.run(_ensure_running(SpawnConfig(port=port)))
    assert daemon.proc is None
    assert daemon.token == "test-token"
    assert daemon.base_url == f"http://127.0.0.1:{port}"


@pytest.mark.parametrize(
    ("model", "base_url", "runs_dir"),
    [
        (None, "http://localhost:8000/v1", None),
        ("holo3-122b", None, None),
        ("holo3-122b", "http://localhost:8000/v1", None),
        (None, None, Path("/tmp/runs")),
    ],
)
def test_attach_with_spawn_flags_fails_fast(
    monkeypatch: pytest.MonkeyPatch, model: str | None, base_url: str | None, runs_dir: Path | None
) -> None:
    # Even with a valid token, attaching must refuse: the running server keeps
    # the configuration it was started with, so the flags cannot apply.
    monkeypatch.setenv(AUTH_TOKEN_ENV, "test-token")
    with _fake_agent_server() as port, pytest.raises(RuntimeError, match="already running"):
        asyncio.run(_ensure_running(SpawnConfig(port=port, model=model, base_url=base_url, runs_dir=runs_dir)))


def test_attach_with_fake_fails_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    # --fake only reaches a freshly spawned binary; attaching would silently
    # run the "fake" client against a real model and desktop.
    monkeypatch.setenv(AUTH_TOKEN_ENV, "test-token")
    with _fake_agent_server() as port, pytest.raises(RuntimeError, match="already running") as excinfo:
        asyncio.run(_ensure_running(SpawnConfig(port=port, fake=True)))
    assert "--fake" in str(excinfo.value)


def test_attach_with_env_model_config_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    # Model/base-url from ~/.holo/.env are spawn defaults for stdio servers, not
    # explicit CLI flags. They should not block attaching to an already-running
    # local runtime.
    monkeypatch.setenv(AUTH_TOKEN_ENV, "test-token")
    monkeypatch.setenv(launcher.PORT_ENV, "0")
    monkeypatch.setenv("HAI_AGENT_RUNTIME_MODEL", "holo3-local")
    monkeypatch.setenv("HAI_AGENT_RUNTIME_BASE_URL", "http://127.0.0.1:8000/v1")
    with _fake_agent_server() as port:
        monkeypatch.setenv(launcher.PORT_ENV, str(port))
        daemon = asyncio.run(launcher.ensure_running_from_env())
    assert daemon.proc is None
    assert daemon.token == "test-token"
    assert daemon.base_url == f"http://127.0.0.1:{port}"


def test_attach_with_env_fast_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    # `fast`/`fake` from the environment are ambient spawn defaults for stdio
    # servers, not explicit CLI flags; a shared server may already be fast, so
    # they must not block attaching to an already-running local runtime.
    monkeypatch.setenv(AUTH_TOKEN_ENV, "test-token")
    monkeypatch.setenv("HAI_AGENT_RUNTIME_FAST", "1")
    with _fake_agent_server() as port:
        monkeypatch.setenv(launcher.PORT_ENV, str(port))
        daemon = asyncio.run(launcher.ensure_running_from_env())
    assert daemon.proc is None
    assert daemon.base_url == f"http://127.0.0.1:{port}"


def test_attach_with_cli_fast_fails_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    # An explicit `--fast` (CLI path, require_fresh_for_config=True) must still
    # refuse to attach: the running server keeps its own quality settings.
    monkeypatch.setenv(AUTH_TOKEN_ENV, "test-token")
    with _fake_agent_server() as port, pytest.raises(RuntimeError, match="already running") as excinfo:
        asyncio.run(_ensure_running(SpawnConfig(port=port, fast=True)))
    assert "--fast" in str(excinfo.value)


def test_attach_error_names_the_rejected_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(AUTH_TOKEN_ENV, "test-token")
    with _fake_agent_server() as port, pytest.raises(RuntimeError) as excinfo:
        asyncio.run(
            _ensure_running(
                SpawnConfig(
                    port=port,
                    model="holo3-122b",
                    base_url="http://localhost:8000/v1",
                    runs_dir=Path("/tmp/runs"),
                )
            )
        )
    message = str(excinfo.value)
    assert "--model" in message
    assert "--base-url" in message
    assert "--runs-dir" in message
    assert "--port" in message  # the error must point at a way out


def test_attach_without_token_still_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Pre-existing contract: attaching with no env token and no token file is an error.
    monkeypatch.delenv(AUTH_TOKEN_ENV, raising=False)
    monkeypatch.setattr(launcher, "TOKEN_DIR", tmp_path)
    with _fake_agent_server() as port, pytest.raises(RuntimeError, match=AUTH_TOKEN_ENV):
        asyncio.run(_ensure_running(SpawnConfig(port=port)))


def test_attach_captures_runtime_version_and_warns_on_mismatch(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv(AUTH_TOKEN_ENV, "test-token")
    body = json.dumps({"status": "ok", "version": "999.0.0"}).encode()
    with _fake_agent_server(health_body=body) as port, caplog.at_level(logging.WARNING):
        daemon = asyncio.run(_ensure_running(SpawnConfig(port=port)))
    assert daemon.runtime_version == "999.0.0"
    warning = next(r for r in caplog.records if r.levelno == logging.WARNING)
    assert "999.0.0" in warning.getMessage()
    assert PINNED_RUNTIME_VERSION in warning.getMessage()


def test_attach_with_matching_version_does_not_warn(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv(AUTH_TOKEN_ENV, "test-token")
    body = json.dumps({"status": "ok", "version": PINNED_RUNTIME_VERSION}).encode()
    with _fake_agent_server(health_body=body) as port, caplog.at_level(logging.WARNING):
        daemon = asyncio.run(_ensure_running(SpawnConfig(port=port)))
    assert daemon.runtime_version == PINNED_RUNTIME_VERSION
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


def test_attach_tolerates_versionless_health_body(monkeypatch: pytest.MonkeyPatch) -> None:
    # PATH/dev binaries and stubs may serve an empty /health; no version, no warning, no crash.
    monkeypatch.setenv(AUTH_TOKEN_ENV, "test-token")
    with _fake_agent_server() as port:
        daemon = asyncio.run(_ensure_running(SpawnConfig(port=port)))
    assert daemon.runtime_version is None


def test_runtime_child_env_keeps_portal_key_without_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAI_API_KEY", "portal-key")
    monkeypatch.delenv("HAI_AGENT_RUNTIME_BASE_URL", raising=False)
    assert launcher.runtime_child_env({}, settings=launcher.load_holo_settings())["HAI_API_KEY"] == "portal-key"


def test_runtime_child_env_strips_portal_key_for_explicit_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAI_API_KEY", "portal-key")
    monkeypatch.delenv("HAI_AGENT_RUNTIME_BASE_URL", raising=False)
    env = launcher.runtime_child_env(
        {"HAI_AGENT_RUNTIME_BASE_URL": "http://localhost:8000/v1"}, settings=launcher.load_holo_settings()
    )
    assert "HAI_API_KEY" not in env


def test_runtime_child_env_strips_portal_key_for_inherited_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    # The base URL comes from ~/.holo/.env (inherited via os.environ), not a passed flag.
    monkeypatch.setenv("HAI_API_KEY", "portal-key")
    monkeypatch.setenv("HAI_AGENT_RUNTIME_BASE_URL", "http://localhost:8000/v1")
    assert "HAI_API_KEY" not in launcher.runtime_child_env({}, settings=launcher.load_holo_settings())


def test_runtime_child_env_treats_whitespace_base_url_as_hosted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAI_API_KEY", "portal-key")
    monkeypatch.setenv("HAI_AGENT_RUNTIME_BASE_URL", " ")
    monkeypatch.delenv(launcher.MODELS_API_BASE_URL_ENV, raising=False)

    env = launcher.runtime_child_env({}, settings=launcher.load_holo_settings())

    assert env["HAI_API_KEY"] == "portal-key"
    assert env[launcher.MODELS_API_BASE_URL_ENV] == launcher.PRODUCTION_GATEWAY_URL
    assert "HAI_AGENT_RUNTIME_BASE_URL" not in env


def test_spawn_config_from_env_ignores_whitespace_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAI_AGENT_RUNTIME_PORT", "12345")
    monkeypatch.setenv("HAI_AGENT_RUNTIME_BASE_URL", " ")

    config = launcher.spawn_config_from_env(settings=launcher.load_holo_settings())

    assert config.base_url is None
