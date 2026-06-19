"""Behavioural tests for `holo doctor` environment diagnostics.

Each check runs against tmp-path ``~/.holo`` fixtures and a real loopback
/health server; the command exits 0 only when every check passes and points
at a concrete fix otherwise.
"""

from __future__ import annotations

import importlib
import json
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import pytest

from holo_desktop import customization
from holo_desktop.agent_client import launcher, runtime_install
from holo_desktop.cli import bootstrap
from holo_desktop.settings import load_holo_settings

# `holo_desktop.cli.__init__` re-exports the `doctor` command function under
# the same name as the submodule; go through importlib to get the module.
doctor = importlib.import_module("holo_desktop.cli.doctor")


@contextmanager
def _fake_agent_server(version: str) -> Iterator[int]:
    body = json.dumps({"status": "ok", "version": version}).encode()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path != "/health":
                self.send_response(404)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:  # stdlib signature; silences request logs
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()
        thread.join(timeout=5.0)


@pytest.fixture()
def holo_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(runtime_install, "RUNTIME_DIR", tmp_path / "runtime")
    monkeypatch.setattr(launcher, "TOKEN_DIR", tmp_path / "tokens")
    monkeypatch.setattr(launcher, "LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(customization, "SKILLS_DIR", tmp_path / "skills")
    monkeypatch.setattr(bootstrap, "USER_ENV_PATH", tmp_path / ".env")
    monkeypatch.delenv(launcher.AUTH_TOKEN_ENV, raising=False)
    monkeypatch.delenv("HAI_API_KEY", raising=False)
    monkeypatch.delenv("HAI_AGENT_RUNTIME_BASE_URL", raising=False)
    monkeypatch.setenv("PATH", str(tmp_path / "empty-path"))
    return tmp_path


def _by_name(results: list[doctor.CheckResult]) -> dict[str, doctor.CheckResult]:
    return {r.name: r for r in results}


def _run_checks() -> list[doctor.CheckResult]:
    return doctor.run_checks(load_holo_settings())


def _seed_skill(holo_home: Path) -> None:
    skill = holo_home / "skills" / "demo" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("---\ndescription: d\n---\nbody\n", encoding="utf-8")


def _seed_managed_install(holo_home: Path) -> Path:
    version_dir = holo_home / "runtime" / runtime_install.PINNED_RUNTIME_VERSION
    version_dir.mkdir(parents=True)
    binary = version_dir / runtime_install.BINARY_NAME
    binary.write_bytes(b"#!/bin/sh\n")
    binary.chmod(0o755)
    return binary


def test_all_green_environment_passes(holo_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAI_API_KEY", "key")
    _seed_managed_install(holo_home)
    _seed_skill(holo_home)

    with _fake_agent_server(runtime_install.PINNED_RUNTIME_VERSION) as port:
        monkeypatch.setenv(launcher.PORT_ENV, str(port))
        monkeypatch.setenv(launcher.AUTH_TOKEN_ENV, "token")
        results = _run_checks()

    assert all(r.ok for r in results), [f"{r.name}: {r.detail}" for r in results if not r.ok]


def test_missing_binary_fails_with_pointer(holo_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAI_API_KEY", "key")
    monkeypatch.setenv(launcher.PORT_ENV, "1")  # nothing listens here
    results = _by_name(_run_checks())

    binary = results["binary"]
    assert not binary.ok
    assert binary.fix is not None


def test_binary_env_var_is_ignored(holo_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # The removed HAI_AGENT_RUNTIME_BINARY escape hatch must not green-light the binary check.
    monkeypatch.setenv("HAI_API_KEY", "key")
    monkeypatch.setenv(launcher.PORT_ENV, "1")
    monkeypatch.setenv("HAI_AGENT_RUNTIME_BINARY", "python -m hai_agent_runtime")
    assert not _by_name(_run_checks())["binary"].ok


def test_managed_install_is_reported(holo_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAI_API_KEY", "key")
    monkeypatch.setenv(launcher.PORT_ENV, "1")
    binary = _seed_managed_install(holo_home)

    result = _by_name(_run_checks())["binary"]
    assert result.ok
    assert str(binary) in result.detail


def test_missing_credentials_fail_login_check(holo_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(launcher.PORT_ENV, "1")
    result = _by_name(_run_checks())["login"]
    assert not result.ok
    assert result.fix is not None and "holo login" in result.fix


def test_running_server_without_token_fails_agent_api_check(holo_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAI_API_KEY", "key")
    with _fake_agent_server("1.2.3") as port:
        monkeypatch.setenv(launcher.PORT_ENV, str(port))
        result = _by_name(_run_checks())["agent-api"]
    assert not result.ok
    assert launcher.AUTH_TOKEN_ENV in (result.fix or "")


def test_idle_port_is_not_a_failure(holo_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # No server running is the normal state: every surface spawns on demand.
    monkeypatch.setenv("HAI_API_KEY", "key")
    monkeypatch.setenv(launcher.PORT_ENV, "1")
    result = _by_name(_run_checks())["agent-api"]
    assert result.ok


PORT = 23498  # pinned: the log file `permissions_guidance_needed` inspects is keyed by port


@pytest.mark.skipif(sys.platform != "darwin", reason="TCC guidance is macOS-only")
def test_permissions_guidance_shown_while_managed_first_run_pending(holo_home: Path) -> None:
    # No first-run marker and no `hai-agent-runtime` on PATH: grants were almost certainly never given.
    assert doctor.permissions_guidance_needed(PORT)


@pytest.mark.skipif(sys.platform != "darwin", reason="TCC guidance is macOS-only")
def test_permissions_guidance_hidden_after_first_run_completes(holo_home: Path) -> None:
    runtime_install.mark_first_run_complete(runtime_install.PINNED_RUNTIME_VERSION)
    assert not doctor.permissions_guidance_needed(PORT)


@pytest.mark.skipif(sys.platform != "darwin", reason="TCC guidance is macOS-only")
def test_permissions_guidance_reappears_on_permission_shaped_log(holo_home: Path) -> None:
    runtime_install.mark_first_run_complete(runtime_install.PINNED_RUNTIME_VERSION)
    log_dir = holo_home / "logs"
    log_dir.mkdir()
    (log_dir / f"hai-agent-runtime-{PORT}.log").write_text("screen recording denied by TCC\n", encoding="utf-8")
    assert doctor.permissions_guidance_needed(PORT)


@pytest.mark.skipif(sys.platform != "darwin", reason="TCC guidance is macOS-only")
def test_permissions_guidance_hidden_for_path_binary(holo_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # A dev binary on PATH never gets a first-run marker; without this gate the panel would show forever.
    bin_dir = holo_home / "bin"
    bin_dir.mkdir()
    binary = bin_dir / "hai-agent-runtime"
    binary.write_bytes(b"#!/bin/sh\n")
    binary.chmod(0o755)
    monkeypatch.setenv("PATH", str(bin_dir))
    assert not doctor.permissions_guidance_needed(PORT)


@pytest.mark.skipif(sys.platform == "darwin", reason="covers the non-macOS branch")
def test_permissions_guidance_never_shown_off_macos(holo_home: Path) -> None:
    assert not doctor.permissions_guidance_needed(PORT)


@pytest.mark.skipif(sys.platform != "darwin", reason="TCC guidance is macOS-only")
def test_doctor_output_omits_permissions_panel_when_healthy(
    holo_home: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("HAI_API_KEY", "key")
    monkeypatch.setenv(launcher.PORT_ENV, str(PORT))
    _seed_managed_install(holo_home)
    _seed_skill(holo_home)
    runtime_install.mark_first_run_complete(runtime_install.PINNED_RUNTIME_VERSION)

    doctor.doctor()
    assert "macOS permissions" not in capsys.readouterr().out


def test_doctor_exit_codes(holo_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(launcher.PORT_ENV, "1")
    with pytest.raises(SystemExit) as excinfo:
        doctor.doctor()
    assert excinfo.value.code == 1

    monkeypatch.setenv("HAI_API_KEY", "key")
    _seed_managed_install(holo_home)
    _seed_skill(holo_home)
    doctor.doctor()  # all green: returns normally (exit 0)
