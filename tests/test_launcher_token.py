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
import socket
import stat
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import pytest
from hai_agents_local.runtime.state import token_file_path

from holo_desktop.agent_client import launcher

from ._runtime_stub import SCRIPT, ProvingHandler


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _use_stub(monkeypatch: pytest.MonkeyPatch) -> None:
    # The binary-resolution seam: resolution itself is covered in test_runtime_install.py.
    monkeypatch.setattr(launcher, "resolve_command", lambda **_: [sys.executable, SCRIPT])
    monkeypatch.delenv(launcher.AUTH_TOKEN_ENV, raising=False)


async def _ensure_running(config: launcher.SpawnConfig) -> launcher.AgentDaemon:
    return await launcher.ensure_running(config, settings=launcher.load_holo_settings())


@contextmanager
def _fake_agent_server(token: str) -> Iterator[int]:
    class Handler(ProvingHandler):
        def do_GET(self) -> None:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"status":"ok","recipe":"shared"}')

    Handler.token = token
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()
        thread.join(timeout=5.0)


@pytest.mark.timeout(60)
def test_second_client_attaches_with_the_spawners_generated_token(monkeypatch: pytest.MonkeyPatch) -> None:
    # The reported bug: spawner generates a token, second CLI on the same port
    # has no env token — it must still be able to authenticate.
    _use_stub(monkeypatch)
    port = _free_port()

    async def flow() -> None:
        spawned = await _ensure_running(launcher.SpawnConfig(port=port, fake=True))
        try:
            attached = await _ensure_running(launcher.SpawnConfig(port=port))
            assert not attached.runtime.owned
            assert attached.runtime.api_key == spawned.runtime.api_key
        finally:
            await spawned.aclose()

    asyncio.run(flow())


@pytest.mark.timeout(60)
def test_spawn_persists_generated_token_with_owner_only_perms(monkeypatch: pytest.MonkeyPatch) -> None:
    _use_stub(monkeypatch)
    port = _free_port()

    async def flow() -> None:
        daemon = await _ensure_running(launcher.SpawnConfig(port=port, fake=True))
        try:
            token_file = token_file_path(port)
            assert token_file.read_text(encoding="utf-8").strip() == daemon.runtime.api_key
            if sys.platform != "win32":
                assert stat.S_IMODE(token_file.stat().st_mode) == 0o600
        finally:
            await daemon.aclose()

    asyncio.run(flow())


@pytest.mark.timeout(60)
def test_spawned_daemon_removes_its_token_file_on_close(monkeypatch: pytest.MonkeyPatch) -> None:
    _use_stub(monkeypatch)
    port = _free_port()

    async def flow() -> None:
        daemon = await _ensure_running(launcher.SpawnConfig(port=port, fake=True))
        await daemon.aclose()

    asyncio.run(flow())
    assert not token_file_path(port).exists()


@pytest.mark.timeout(60)
def test_spawn_with_explicit_env_token_writes_nothing_to_disk(monkeypatch: pytest.MonkeyPatch) -> None:
    # A user-supplied secret must never silently land on disk.
    _use_stub(monkeypatch)
    monkeypatch.setenv(launcher.AUTH_TOKEN_ENV, "user-secret")
    port = _free_port()

    async def flow() -> None:
        daemon = await _ensure_running(launcher.SpawnConfig(port=port, fake=True))
        try:
            assert daemon.runtime.api_key == "user-secret"
        finally:
            await daemon.aclose()

    asyncio.run(flow())
    assert not token_file_path(port).exists()


def _publish_token(port: int, token: str) -> Path:
    path = token_file_path(port)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(token, encoding="utf-8")
    return path


def test_attach_env_token_wins_over_token_file(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(launcher.AUTH_TOKEN_ENV, "env-token")
    with _fake_agent_server("env-token") as port:
        _publish_token(port, "file-token")
        daemon = asyncio.run(_ensure_running(launcher.SpawnConfig(port=port)))
    assert daemon.runtime.api_key == "env-token"


def test_attaching_client_never_deletes_the_token_file(monkeypatch: pytest.MonkeyPatch) -> None:
    # Only the spawner owns the file; an attach-then-close must leave it for other clients.
    monkeypatch.delenv(launcher.AUTH_TOKEN_ENV, raising=False)
    with _fake_agent_server("file-token") as port:
        token_file = _publish_token(port, "file-token")

        async def attach_and_close() -> None:
            daemon = await _ensure_running(launcher.SpawnConfig(port=port))
            assert daemon.runtime.api_key == "file-token"
            await daemon.aclose()

        asyncio.run(attach_and_close())
        assert token_file.exists()


def test_attach_without_env_or_file_names_both_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(launcher.AUTH_TOKEN_ENV, raising=False)
    with _fake_agent_server("unknown") as port, pytest.raises(RuntimeError) as excinfo:
        asyncio.run(_ensure_running(launcher.SpawnConfig(port=port)))
    message = str(excinfo.value)
    assert launcher.AUTH_TOKEN_ENV in message
    assert str(token_file_path(port)) in message
