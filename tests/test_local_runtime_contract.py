"""Contract tests pinning the hai-agents local-runtime behaviors Holo relies on.

Ported from tests/test_launcher_spawn.py, test_launcher_token.py, and
test_launcher_pid.py before those files (and the launcher/runtime_install
implementations they cover) are deleted in Task 9. Each test names the
launcher test it replaces; together they are the spec the SDK must keep
honoring for HoloDesktop. Failures here are upstream hai-agents bugs
(plan 002), not Holo bugs.
"""

from __future__ import annotations

import os
import socket
import stat
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

from hai_agents.local import LocalRuntime

# Serves 200 on every GET so the SDK's /health handshake succeeds.
# (Verbatim from tests/test_launcher_token.py.)
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

# Exits 2 after complaining on stderr; never serves /health.
# (Verbatim from tests/test_launcher_spawn.py.)
CRASHING_BINARY = textwrap.dedent(
    """
    import sys
    print("fatal: no desktop session available", file=sys.stderr)
    sys.exit(2)
    """
)

# Floods stderr past any platform's pipe capacity (~64KB) BEFORE serving /health.
# (Verbatim from tests/test_launcher_spawn.py — the chatty-binary deadlock spec.)
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

# Writes its pid to a file, never serves /health: lets a test time out
# ensure_started and then assert the child was terminated, not leaked.
NEVER_HEALTHY_BINARY = textwrap.dedent(
    """
    import os, time
    with open(os.environ["STUB_PID_FILE"], "w", encoding="utf-8") as fh:
        fh.write(str(os.getpid()))
    time.sleep(120)
    """
)


@pytest.fixture(autouse=True)
def _sanitize_local_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ambient runtime config must not leak into the contract: each test picks its own port/cache."""
    for name in (
        "HAI_AGENT_RUNTIME_API_TOKEN",
        "HAI_AGENT_RUNTIME_PORT",
        "HAI_AGENT_LOCAL_BASE_URL",
        "HAI_AGENT_LOCAL_BINARY_PATH",
        "HAI_AGENT_LOCAL_CACHE_DIR",
    ):
        monkeypatch.delenv(name, raising=False)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _stub_binary(tmp_path: Path, source: str) -> Path:
    """An executable wrapper around a Python stub (binary_path takes one path)."""
    script = tmp_path / "stub_runtime.py"
    script.write_text(source, encoding="utf-8")
    if os.name == "nt":
        wrapper = tmp_path / "stub-runtime.cmd"
        wrapper.write_text(f'@echo off\r\n"{sys.executable}" "{script}" %*\r\n', encoding="utf-8")
    else:
        wrapper = tmp_path / "stub-runtime"
        wrapper.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{script}" "$@"\n', encoding="utf-8")
        wrapper.chmod(0o755)
    return wrapper


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


def test_attach_returns_none_when_no_runtime_listens(tmp_path: Path) -> None:
    # Replaces the launcher's "spawn when /health is unreachable" branch: no
    # discovery state + nothing listening must read as "no runtime", never a
    # half-alive handle.
    assert LocalRuntime.attach(port=_free_port(), cache_dir=tmp_path) is None


@pytest.mark.timeout(60)
def test_spawn_failure_reports_stderr_from_log(tmp_path: Path) -> None:
    # Replaces test_launcher_spawn.test_spawn_failure_reports_stderr_from_log:
    # a binary that dies before /health must surface its stderr in the error.
    with pytest.raises(Exception, match="no desktop session available"):
        LocalRuntime.ensure_started(
            binary_path=_stub_binary(tmp_path, CRASHING_BINARY),
            cache_dir=tmp_path / "cache",
            port=_free_port(),
            download=False,
        )


@pytest.mark.timeout(60)
def test_spawn_survives_chatty_stderr(tmp_path: Path) -> None:
    # Replaces test_launcher_spawn.test_spawn_survives_chatty_stderr: stderr
    # must land in a log file, not a pipe nobody drains, or a chatty binary
    # blocks before ever becoming healthy.
    runtime = LocalRuntime.ensure_started(
        binary_path=_stub_binary(tmp_path, CHATTY_BINARY),
        cache_dir=tmp_path / "cache",
        port=_free_port(),
        download=False,
    )
    try:
        assert runtime.owned is True
        log_path = runtime.log_path
    finally:
        runtime.shutdown()
    assert log_path is not None
    # Past any platform's pipe buffer (~64KB), proving the flood wrote without blocking.
    assert log_path.stat().st_size > 200 * 1024


@pytest.mark.timeout(60)
def test_failed_spawn_never_leaks_the_child(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Replaces test_launcher_spawn.test_cancellation_mid_spawn_terminates_the_child,
    # restated for the SDK's sync spawn: when ensure_started gives up (timeout),
    # the child it started must be terminated, never left running.
    pid_file = tmp_path / "stub.pid"
    monkeypatch.setenv("STUB_PID_FILE", str(pid_file))

    with pytest.raises(Exception):
        LocalRuntime.ensure_started(
            binary_path=_stub_binary(tmp_path, NEVER_HEALTHY_BINARY),
            cache_dir=tmp_path / "cache",
            port=_free_port(),
            download=False,
            timeout_s=3.0,
        )

    pid = int(pid_file.read_text(encoding="utf-8"))
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        if not _pid_alive(pid):
            return
        time.sleep(0.1)
    _force_kill(pid)  # don't leave the leak behind even when failing
    pytest.fail(f"spawned binary (pid {pid}) survived a failed ensure_started")


@pytest.mark.timeout(60)
def test_second_client_attaches_with_the_spawners_credentials(tmp_path: Path) -> None:
    # Replaces test_launcher_token.test_second_client_attaches_with_the_spawners_generated_token:
    # holo run must be able to attach to a runtime holo serve spawned.
    cache = tmp_path / "cache"
    port = _free_port()
    spawned = LocalRuntime.ensure_started(
        binary_path=_stub_binary(tmp_path, HEALTHY_BINARY), cache_dir=cache, port=port, download=False
    )
    try:
        attached = LocalRuntime.attach(port=port, cache_dir=cache)
        assert attached is not None
        assert attached.owned is False, "an attacher must never think it owns the process"
        assert attached.api_key == spawned.api_key
    finally:
        spawned.shutdown()


@pytest.mark.timeout(60)
def test_persisted_credentials_are_owner_only(tmp_path: Path) -> None:
    # Replaces test_launcher_token.test_spawn_persists_generated_token_with_owner_only_perms
    # and test_launcher_pid.test_pid_file_written_owner_only, without pinning the
    # SDK's on-disk layout: any state file carrying the bearer credential is 0600.
    if sys.platform == "win32":
        pytest.skip("POSIX file-mode semantics")
    cache = tmp_path / "cache"
    runtime = LocalRuntime.ensure_started(
        binary_path=_stub_binary(tmp_path, HEALTHY_BINARY), cache_dir=cache, port=_free_port(), download=False
    )
    try:
        carriers = [
            p
            for p in cache.rglob("*")
            if p.is_file() and runtime.api_key in p.read_text(encoding="utf-8", errors="replace")
        ]
        assert carriers, "the credential must be discoverable on disk for cross-process attach"
        for path in carriers:
            assert stat.S_IMODE(path.stat().st_mode) == 0o600, path
    finally:
        runtime.shutdown()


@pytest.mark.timeout(60)
def test_attach_ignores_stale_state_after_unclean_death(tmp_path: Path) -> None:
    # Replaces the stale-pid gotcha documented on launcher.discover_runtime_pids:
    # a runtime that died uncleanly leaves state behind; attach must probe and
    # report None, never hand back a dead runtime as live.
    cache = tmp_path / "cache"
    port = _free_port()
    runtime = LocalRuntime.ensure_started(
        binary_path=_stub_binary(tmp_path, HEALTHY_BINARY), cache_dir=cache, port=port, download=False
    )
    pid = runtime.pid
    assert pid is not None
    # Kill out-of-band (no SDK cleanup) so the token/pid state files stay behind, stale.
    _force_kill(pid)
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline and _pid_alive(pid):
        time.sleep(0.1)
    assert LocalRuntime.attach(port=port, cache_dir=cache) is None


@pytest.mark.timeout(60)
def test_attach_env_token_wins_over_persisted_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Replaces test_launcher_token.test_attach_env_token_wins_over_token_file:
    # an explicit HAI_AGENT_RUNTIME_API_TOKEN overrides discovered credentials.
    cache = tmp_path / "cache"
    port = _free_port()
    runtime = LocalRuntime.ensure_started(
        binary_path=_stub_binary(tmp_path, HEALTHY_BINARY), cache_dir=cache, port=port, download=False
    )
    try:
        monkeypatch.setenv("HAI_AGENT_RUNTIME_API_TOKEN", "env-token")
        attached = LocalRuntime.attach(port=port, cache_dir=cache)
        assert attached is not None
        assert attached.api_key == "env-token"
    finally:
        runtime.shutdown()
