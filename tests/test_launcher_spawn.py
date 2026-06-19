"""Behavioural tests for the spawn path's stderr handling.

The binary's stderr must go to a log file, not a pipe: nobody drains a pipe
after a successful spawn, so a chatty binary would fill the ~64KB buffer and
block mid-run. The log file also has to feed the spawn-failure error message.
"""

from __future__ import annotations

import asyncio
import os
import socket
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

from holo_desktop.agent_client import launcher

# Exits 2 after complaining on stderr; never serves /health.
CRASHING_BINARY = textwrap.dedent(
    """
    import sys
    print("fatal: no desktop session available", file=sys.stderr)
    sys.exit(2)
    """
)

# Floods stderr past any platform's pipe capacity (~64KB) BEFORE serving /health:
# with a pipe nobody drains, the child blocks on write and never becomes healthy.
# 256KB is comfortably past the buffer while keeping the pre-health write cheap, so
# the healthy path stays fast even on a heavily contended CI runner.
CHATTY_BINARY = textwrap.dedent(
    """
    import os, sys
    from http.server import BaseHTTPRequestHandler, HTTPServer

    for _ in range(256):
        sys.stderr.write("x" * 1024 + "\\n")
    sys.stderr.flush()

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


# Writes its pid to a file, never serves /health: lets a test cancel
# ensure_running mid-spawn and then assert the child was terminated.
NEVER_HEALTHY_BINARY = textwrap.dedent(
    """
    import os, time
    with open(os.environ["STUB_PID_FILE"], "w", encoding="utf-8") as fh:
        fh.write(str(os.getpid()))
    time.sleep(120)
    """
)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _use_stub(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, source: str) -> None:
    script = tmp_path / "stub_runtime.py"
    script.write_text(source, encoding="utf-8")
    # The binary-resolution seam: resolution itself is covered in test_runtime_install.py.
    monkeypatch.setattr(launcher, "resolve_command", lambda **_: [sys.executable, str(script)])
    monkeypatch.delenv(launcher.AUTH_TOKEN_ENV, raising=False)
    monkeypatch.setattr(launcher, "LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(launcher, "TOKEN_DIR", tmp_path / "tokens")


async def _ensure_running(config: launcher.SpawnConfig) -> launcher.AgentDaemon:
    return await launcher.ensure_running(config, settings=launcher.load_holo_settings())


@pytest.mark.timeout(60)
def test_spawn_failure_reports_stderr_from_log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _use_stub(tmp_path, monkeypatch, CRASHING_BINARY)

    with pytest.raises(RuntimeError, match="no desktop session available"):
        asyncio.run(_ensure_running(launcher.SpawnConfig(port=_free_port(), fake=True)))


@pytest.mark.timeout(60)
def test_cancellation_mid_spawn_terminates_the_child(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Ctrl+C while the health poll is still waiting cancels ensure_running;
    # the freshly spawned binary must not be left running.
    _use_stub(tmp_path, monkeypatch, NEVER_HEALTHY_BINARY)
    pid_file = tmp_path / "stub.pid"
    monkeypatch.setenv("STUB_PID_FILE", str(pid_file))

    async def spawn_then_cancel() -> None:
        task = asyncio.ensure_future(_ensure_running(launcher.SpawnConfig(port=_free_port(), fake=True)))
        while not pid_file.exists():  # binary is up; health poll is now spinning
            await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(spawn_then_cancel())

    pid = int(pid_file.read_text(encoding="utf-8"))
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        if not _pid_alive(pid):
            return  # child is gone
        time.sleep(0.1)
    _force_kill(pid)  # don't leave the leak behind even when failing
    pytest.fail(f"spawned binary (pid {pid}) survived cancellation of ensure_running")


def _pid_alive(pid: int) -> bool:
    # os.kill(pid, 0) is a liveness probe on POSIX only; on Windows signal 0 is
    # TerminateProcess(pid, 0) — it would KILL the process we are checking.
    if sys.platform == "win32":
        import ctypes

        process_query_limited_information = 0x1000
        still_active = 259
        handle = ctypes.windll.kernel32.OpenProcess(process_query_limited_information, False, pid)
        if not handle:
            return False
        try:
            exit_code = ctypes.c_ulong()
            ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
            return exit_code.value == still_active
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _force_kill(pid: int) -> None:
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True, check=False)
        return
    os.kill(pid, 9)


@pytest.mark.timeout(60)
def test_spawn_survives_chatty_stderr(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _use_stub(tmp_path, monkeypatch, CHATTY_BINARY)
    # Use the production spawn timeout (the @pytest.mark.timeout below still bounds a true
    # hang). An artificially tight override false-failed on contended macOS CI runners,
    # where interpreter launch + health poll alone can exceed a low limit.

    async def spawn_and_stop() -> None:
        daemon = await _ensure_running(launcher.SpawnConfig(port=_free_port(), fake=True))
        await daemon.aclose()

    asyncio.run(spawn_and_stop())

    logs = list((tmp_path / "logs").glob("hai-agent-runtime-*.log"))
    assert logs, "spawn must leave the binary's stderr in a log file"
    # Past any platform's pipe buffer (~64KB), proving the flood wrote without blocking.
    assert logs[0].stat().st_size > 200 * 1024
