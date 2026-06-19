"""Behavioural tests for the spawn-time env contract with the hai-agent-runtime binary.

The binary owns JSONL persistence (``HAI_AGENT_RUNTIME_RUNS_DIR``, default
``~/.holo/runs``); the client's job is to forward an explicit ``--runs-dir``
to a binary it spawns. The attach-path refusals live in ``test_launcher.py``.
"""

from __future__ import annotations

import asyncio
import json
import socket
import sys
import textwrap
from pathlib import Path

import pytest

from holo_desktop.agent_client import launcher

# Dumps its HAI_AGENT_RUNTIME_* env to a file, then serves 200 on every GET so
# ensure_running's /health handshake succeeds. A stand-in for the real binary.
STUB_BINARY = textwrap.dedent(
    """
    import json, os
    from http.server import BaseHTTPRequestHandler, HTTPServer

    dump = {k: v for k, v in os.environ.items() if k.startswith("HAI_AGENT_RUNTIME_") or k == "HAI_BASE_URL"}
    with open(os.environ["STUB_ENV_DUMP"], "w", encoding="utf-8") as fh:
        json.dump(dump, fh)

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


def _use_stub(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the launcher at the env-dumping stub; returns the dump path."""
    script = tmp_path / "stub_runtime.py"
    script.write_text(STUB_BINARY, encoding="utf-8")
    dump_path = tmp_path / "env.json"
    # The binary-resolution seam: resolution itself is covered in test_runtime_install.py.
    monkeypatch.setattr(launcher, "resolve_command", lambda **_: [sys.executable, str(script)])
    monkeypatch.setenv("STUB_ENV_DUMP", str(dump_path))
    monkeypatch.delenv(launcher.AUTH_TOKEN_ENV, raising=False)
    monkeypatch.setattr(launcher, "TOKEN_DIR", tmp_path / "tokens")
    return dump_path


async def _ensure_running(config: launcher.SpawnConfig) -> launcher.AgentDaemon:
    return await launcher.ensure_running(config, settings=launcher.load_holo_settings())


@pytest.mark.timeout(60)
def test_spawn_forwards_runs_dir_to_binary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dump_path = _use_stub(tmp_path, monkeypatch)
    runs_dir = tmp_path / "runs"

    async def spawn_and_stop() -> None:
        daemon = await _ensure_running(
            launcher.SpawnConfig(
                port=_free_port(),
                model="holo3-test",
                base_url="http://127.0.0.1:8000/v1",
                fake=True,
                runs_dir=runs_dir,
            )
        )
        await daemon.aclose()

    asyncio.run(spawn_and_stop())

    env = json.loads(dump_path.read_text(encoding="utf-8"))
    assert env["HAI_AGENT_RUNTIME_RUNS_DIR"] == str(runs_dir)
    assert env["HAI_AGENT_RUNTIME_MODEL"] == "holo3-test"
    assert env["HAI_AGENT_RUNTIME_BASE_URL"] == "http://127.0.0.1:8000/v1"
    assert env["HAI_AGENT_RUNTIME_FAKE"] == "1"
    assert "HAI_BASE_URL" not in env


@pytest.mark.timeout(60)
def test_spawn_defaults_hosted_models_api_to_production(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dump_path = _use_stub(tmp_path, monkeypatch)
    monkeypatch.delenv(launcher.MODELS_API_BASE_URL_ENV, raising=False)

    async def spawn_and_stop() -> None:
        daemon = await _ensure_running(launcher.SpawnConfig(port=_free_port(), fake=True))
        await daemon.aclose()

    asyncio.run(spawn_and_stop())

    env = json.loads(dump_path.read_text(encoding="utf-8"))
    assert env["HAI_BASE_URL"] == launcher.PRODUCTION_GATEWAY_URL


@pytest.mark.timeout(60)
def test_spawn_defaults_blank_hosted_models_api_to_production(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dump_path = _use_stub(tmp_path, monkeypatch)
    monkeypatch.setenv(launcher.MODELS_API_BASE_URL_ENV, " ")

    async def spawn_and_stop() -> None:
        daemon = await _ensure_running(launcher.SpawnConfig(port=_free_port(), fake=True))
        await daemon.aclose()

    asyncio.run(spawn_and_stop())

    env = json.loads(dump_path.read_text(encoding="utf-8"))
    assert env["HAI_BASE_URL"] == launcher.PRODUCTION_GATEWAY_URL


@pytest.mark.timeout(60)
def test_spawn_preserves_hosted_models_api_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dump_path = _use_stub(tmp_path, monkeypatch)
    override = "https://models.example.com/v1/models"
    monkeypatch.setenv(launcher.MODELS_API_BASE_URL_ENV, override)

    async def spawn_and_stop() -> None:
        daemon = await _ensure_running(launcher.SpawnConfig(port=_free_port(), fake=True))
        await daemon.aclose()

    asyncio.run(spawn_and_stop())

    env = json.loads(dump_path.read_text(encoding="utf-8"))
    assert env["HAI_BASE_URL"] == override


@pytest.mark.timeout(60)
def test_spawn_expands_tilde_in_runs_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # A quoted "~/..." survives shell expansion; the binary must never see a literal tilde.
    dump_path = _use_stub(tmp_path, monkeypatch)

    async def spawn_and_stop() -> None:
        daemon = await _ensure_running(
            launcher.SpawnConfig(port=_free_port(), fake=True, runs_dir=Path("~/custom/runs"))
        )
        await daemon.aclose()

    asyncio.run(spawn_and_stop())

    env = json.loads(dump_path.read_text(encoding="utf-8"))
    assert env["HAI_AGENT_RUNTIME_RUNS_DIR"] == str(Path.home() / "custom" / "runs")


@pytest.mark.timeout(60)
def test_spawn_without_runs_dir_leaves_binary_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dump_path = _use_stub(tmp_path, monkeypatch)
    monkeypatch.delenv("HAI_AGENT_RUNTIME_RUNS_DIR", raising=False)

    async def spawn_and_stop() -> None:
        daemon = await _ensure_running(launcher.SpawnConfig(port=_free_port(), fake=True))
        await daemon.aclose()

    asyncio.run(spawn_and_stop())

    env = json.loads(dump_path.read_text(encoding="utf-8"))
    assert "HAI_AGENT_RUNTIME_RUNS_DIR" not in env
