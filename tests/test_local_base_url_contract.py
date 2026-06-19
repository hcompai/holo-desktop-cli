"""Regression coverage for the holo-desktop -> runtime local-model contract.

The unit tests in this repo already prove ``--base-url`` is forwarded as
``HAI_AGENT_RUNTIME_BASE_URL``. This test goes one boundary further when a
runtime source checkout is available: it spawns the real runtime from that
checkout and verifies the configured OpenAI-compatible endpoint is contacted.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import ClassVar

import pytest


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _holo_executable() -> str:
    found = shutil.which("holo")
    if found:
        return found
    candidate = Path(sys.executable).with_name("holo")
    if candidate.exists():
        return str(candidate)
    raise AssertionError("could not locate the 'holo' console script")


def _runtime_checkout() -> Path | None:
    env_path = os.environ.get("HOLO_RUNTIME_CHECKOUT", "").strip()
    candidates = [Path(env_path)] if env_path else []
    repo = Path(__file__).resolve().parents[1]
    candidates.extend(
        [
            repo.parent / "hai" / "hai_agent_runtime",
            repo.parent / "hai_agent_runtime",
        ]
    )
    for candidate in candidates:
        if (candidate / "src" / "hai_agent_runtime" / "factories.py").exists():
            return candidate
    return None


class _FakeOpenAIHandler(BaseHTTPRequestHandler):
    requests_seen: ClassVar[list[str]] = []

    def do_GET(self) -> None:
        type(self).requests_seen.append(f"GET {self.path}")
        if self.path == "/v1/health":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")
            return
        self.send_response(404)
        self.end_headers()

    def do_POST(self) -> None:
        type(self).requests_seen.append(f"POST {self.path}")
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length:
            self.rfile.read(length)
        if self.path == "/v1/chat/completions":
            body = {
                "id": "chatcmpl-test",
                "object": "chat.completion",
                "created": 0,
                "model": "Hcompany/Holo-3.1-35B-A3B",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "done"},
                        "finish_reason": "stop",
                    }
                ],
            }
            payload = json.dumps(body).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        self.send_response(404)
        self.end_headers()

    def log_message(self, *_args: object) -> None:
        return


@pytest.mark.timeout(90)
def test_base_url_reaches_openai_compatible_endpoint(tmp_path: Path) -> None:
    runtime = _runtime_checkout()
    if runtime is None:
        pytest.skip("requires HOLO_RUNTIME_CHECKOUT or a sibling hai_agent_runtime checkout")

    wrapper_dir = tmp_path / "bin"
    wrapper_dir.mkdir()
    wrapper = wrapper_dir / ("hai-agent-runtime.cmd" if os.name == "nt" else "hai-agent-runtime")
    if os.name == "nt":
        wrapper.write_text(
            f'@echo off\r\ncd /d "{runtime!s}" || exit /b 1\r\nuv run hai-agent-runtime %*\r\n',
            encoding="utf-8",
        )
    else:
        wrapper.write_text(
            f'#!/bin/sh\ncd {runtime!s} || exit 1\nexec uv run hai-agent-runtime "$@"\n',
            encoding="utf-8",
        )
    wrapper.chmod(0o755)

    _FakeOpenAIHandler.requests_seen = []
    model_port = _free_port()
    agent_port = _free_port()
    server = ThreadingHTTPServer(("127.0.0.1", model_port), _FakeOpenAIHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        env = {**os.environ, "PATH": f"{wrapper_dir}{os.pathsep}{os.environ.get('PATH', '')}"}
        completed = subprocess.run(
            [
                _holo_executable(),
                "run",
                "--port",
                str(agent_port),
                "--base-url",
                f"http://127.0.0.1:{model_port}/v1",
                "--model",
                "Hcompany/Holo-3.1-35B-A3B",
                "--max-time-s",
                "1",
                "--quiet",
                "Look at the current screen and answer in one short sentence.",
            ],
            capture_output=True,
            text=True,
            timeout=75,
            check=False,
            env=env,
        )
    finally:
        server.shutdown()
        server.server_close()

    combined_output = f"{completed.stdout}\n{completed.stderr}"
    assert "ConfigCompositionException" not in combined_output
    assert "Could not override 'llm.chat_provider.base_url'" not in combined_output
    assert "GET /v1/health" in _FakeOpenAIHandler.requests_seen
