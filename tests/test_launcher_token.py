"""Behavioural tests for the spawn-token handoff between local clients.

When ``ensure_running`` spawns the binary with a *generated* token, a second
client (e.g. ``holo run`` while ``holo serve`` holds the runtime) has no way
to learn it from the environment. The launcher must publish the generated
token to a per-port file so attaching clients can authenticate, and clean it
up when the daemon it spawned stops. Explicit ``HAI_AGENT_RUNTIME_API_TOKEN``
values stay in the env only — the launcher never writes user secrets to disk.
"""

from __future__ import annotations

import asyncio
import logging
import socket
import stat
import sys
import textwrap
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import pytest

from holo_desktop.agent_client import launcher

# Serves 200 on every GET so ensure_running's /health handshake succeeds.
HEALTHY_BINARY = textwrap.dedent(
    """
    import os
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")

        def log_message(self, *args):
            pass

    HTTPServer(("127.0.0.1", int(os.environ["HAI_AGENT_RUNTIME_PORT"])), Handler).serve_forever()
    """
)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _use_stub(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    script = tmp_path / "stub_runtime.py"
    script.write_text(HEALTHY_BINARY, encoding="utf-8")
    # The binary-resolution seam: resolution itself is covered in test_runtime_install.py.
    monkeypatch.setattr(launcher, "resolve_command", lambda **_: [sys.executable, str(script)])
    monkeypatch.delenv(launcher.AUTH_TOKEN_ENV, raising=False)
    monkeypatch.setattr(launcher, "LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(launcher, "TOKEN_DIR", tmp_path / "tokens")


async def _ensure_running(config: launcher.SpawnConfig) -> launcher.AgentDaemon:
    return await launcher.ensure_running(config, settings=launcher.load_holo_settings())


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
def test_second_client_attaches_with_the_spawners_generated_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The reported bug: spawner generates a token, second CLI on the same port
    # has no env token — it must still be able to authenticate.
    _use_stub(tmp_path, monkeypatch)
    port = _free_port()

    async def flow() -> None:
        spawned = await _ensure_running(launcher.SpawnConfig(port=port, fake=True))
        try:
            attached = await _ensure_running(launcher.SpawnConfig(port=port))
            assert attached.proc is None
            assert attached.token == spawned.token
        finally:
            await spawned.aclose()

    asyncio.run(flow())


@pytest.mark.timeout(60)
def test_spawn_persists_generated_token_with_owner_only_perms(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _use_stub(tmp_path, monkeypatch)
    port = _free_port()

    async def flow() -> None:
        daemon = await _ensure_running(launcher.SpawnConfig(port=port, fake=True))
        try:
            token_file = launcher.token_file_path(port)
            assert token_file.read_text(encoding="utf-8").strip() == daemon.token
            if sys.platform != "win32":
                assert stat.S_IMODE(token_file.stat().st_mode) == 0o600
        finally:
            await daemon.aclose()

    asyncio.run(flow())


@pytest.mark.timeout(60)
def test_spawned_daemon_removes_its_token_file_on_close(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _use_stub(tmp_path, monkeypatch)
    port = _free_port()

    async def flow() -> None:
        daemon = await _ensure_running(launcher.SpawnConfig(port=port, fake=True))
        await daemon.aclose()

    asyncio.run(flow())
    assert not launcher.token_file_path(port).exists()


@pytest.mark.timeout(60)
def test_spawn_with_explicit_env_token_writes_nothing_to_disk(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # A user-supplied secret must never silently land on disk.
    _use_stub(tmp_path, monkeypatch)
    monkeypatch.setenv(launcher.AUTH_TOKEN_ENV, "user-secret")
    port = _free_port()

    async def flow() -> None:
        daemon = await _ensure_running(launcher.SpawnConfig(port=port, fake=True))
        try:
            assert daemon.token == "user-secret"
        finally:
            await daemon.aclose()

    asyncio.run(flow())
    assert not launcher.token_file_path(port).exists()


def test_attach_env_token_wins_over_token_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(launcher, "TOKEN_DIR", tmp_path)
    monkeypatch.setenv(launcher.AUTH_TOKEN_ENV, "env-token")
    with _fake_agent_server() as port:
        launcher.token_file_path(port).write_text("file-token", encoding="utf-8")
        daemon = asyncio.run(_ensure_running(launcher.SpawnConfig(port=port)))
    assert daemon.token == "env-token"


def test_attaching_client_never_deletes_the_token_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Only the spawner owns the file; an attach-then-close must leave it for other clients.
    monkeypatch.setattr(launcher, "TOKEN_DIR", tmp_path)
    monkeypatch.delenv(launcher.AUTH_TOKEN_ENV, raising=False)
    with _fake_agent_server() as port:
        launcher.token_file_path(port).write_text("file-token", encoding="utf-8")

        async def attach_and_close() -> None:
            daemon = await _ensure_running(launcher.SpawnConfig(port=port))
            assert daemon.token == "file-token"
            await daemon.aclose()

        asyncio.run(attach_and_close())
        assert launcher.token_file_path(port).exists()


def test_unreadable_token_file_logs_a_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    # A missing file is the normal case and stays quiet; any other OS error
    # (here: the path is a directory) must be surfaced, not swallowed.
    monkeypatch.setattr(launcher, "TOKEN_DIR", tmp_path)
    monkeypatch.delenv(launcher.AUTH_TOKEN_ENV, raising=False)
    port = _free_port()

    with caplog.at_level(logging.WARNING):
        assert launcher._read_token_file(port) == ""
    assert not caplog.records, "a missing token file is expected and must stay quiet"

    launcher.token_file_path(port).mkdir(parents=True)
    with caplog.at_level(logging.WARNING):
        assert launcher._read_token_file(port) == ""
    assert any(str(launcher.token_file_path(port)) in r.getMessage() for r in caplog.records)


def test_attach_without_env_or_file_names_both_sources(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(launcher, "TOKEN_DIR", tmp_path)
    monkeypatch.delenv(launcher.AUTH_TOKEN_ENV, raising=False)
    with _fake_agent_server() as port, pytest.raises(RuntimeError) as excinfo:
        asyncio.run(_ensure_running(launcher.SpawnConfig(port=port)))
    message = str(excinfo.value)
    assert launcher.AUTH_TOKEN_ENV in message
    assert str(launcher.token_file_path(port)) in message
