"""Behavioural tests for `holo doctor` environment diagnostics.

The runtime lifecycle is SDK-owned now, so the agent-api check reads
``LocalRuntime.attach`` state through a fake seam instead of a real loopback
/health server; the command exits 0 only when every check passes and points at
a concrete fix otherwise.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from holo_desktop import customization
from holo_desktop.agent_client import permissions
from holo_desktop.cli import bootstrap
from holo_desktop.settings import AUTH_TOKEN_ENV, load_holo_settings

# `holo_desktop.cli.__init__` re-exports the `doctor` command function under
# the same name as the submodule; go through importlib to get the module.
doctor = importlib.import_module("holo_desktop.cli.doctor")


def _fake_runtime(*, version: str = "0.2.0", healthy: bool = True, api_key: str | None = "k"):
    def health() -> dict:
        if not healthy:
            raise RuntimeError("connection refused")
        return {"status": "ok", "version": version}

    return SimpleNamespace(
        version=version,
        api_key=api_key,
        pid=4242,
        health=health,
        log_path=None,
        owned=False,
        base_url="http://127.0.0.1:18795",
    )


@pytest.fixture()
def holo_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(customization, "SKILLS_DIR", tmp_path / "skills")
    monkeypatch.setattr(bootstrap, "USER_ENV_PATH", tmp_path / ".env")
    monkeypatch.setattr(permissions, "FIRST_RUN_MARKER", tmp_path / "marker" / ".first-run-complete")
    monkeypatch.delenv(AUTH_TOKEN_ENV, raising=False)
    monkeypatch.delenv("HAI_API_KEY", raising=False)
    monkeypatch.delenv("HAI_AGENT_RUNTIME_BASE_URL", raising=False)
    monkeypatch.setenv("PATH", str(tmp_path / "empty-path"))
    # Default: no runtime attached; individual tests override the seam as needed.
    monkeypatch.setattr(doctor.LocalRuntime, "attach", staticmethod(lambda *, port=None, cache_dir=None: None))
    return tmp_path


def _by_name(results: list[doctor.CheckResult]) -> dict[str, doctor.CheckResult]:
    return {r.name: r for r in results}


def _run_checks() -> list[doctor.CheckResult]:
    return doctor.run_checks(load_holo_settings())


def _seed_skill(holo_home: Path) -> None:
    skill = holo_home / "skills" / "demo" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("---\ndescription: d\n---\nbody\n", encoding="utf-8")


def test_all_green_environment_passes(holo_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAI_API_KEY", "key")
    _seed_skill(holo_home)
    monkeypatch.setattr(
        doctor.LocalRuntime, "attach", staticmethod(lambda *, port=None, cache_dir=None: _fake_runtime())
    )
    results = _run_checks()
    assert all(r.ok for r in results), [f"{r.name}: {r.detail}" for r in results if not r.ok]


def test_binary_reports_sdk_managed_when_not_on_path(holo_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAI_API_KEY", "key")
    result = _by_name(_run_checks())["binary"]
    # No local manifest to inspect anymore: install/version pinning is SDK-owned.
    assert result.ok
    assert "SDK" in result.detail


def test_binary_reports_path_install_when_present(holo_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bin_dir = holo_home / "bin"
    bin_dir.mkdir()
    binary = bin_dir / "hai-agent-runtime"
    binary.write_bytes(b"#!/bin/sh\n")
    binary.chmod(0o755)
    monkeypatch.setenv("PATH", str(bin_dir))
    result = _by_name(_run_checks())["binary"]
    assert result.ok
    assert str(binary) in result.detail


def test_missing_credentials_fail_login_check(holo_home: Path) -> None:
    result = _by_name(_run_checks())["login"]
    assert not result.ok
    assert result.fix is not None and "holo login" in result.fix


def test_no_runtime_is_ok_and_says_spawn_on_demand(holo_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAI_API_KEY", "key")
    monkeypatch.setattr(doctor.LocalRuntime, "attach", staticmethod(lambda *, port=None, cache_dir=None: None))
    results = _by_name(_run_checks())
    assert results["agent-api"].ok
    assert "spawns on demand" in results["agent-api"].detail


def test_running_runtime_reports_version_and_credentials(holo_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAI_API_KEY", "key")
    monkeypatch.setattr(
        doctor.LocalRuntime, "attach", staticmethod(lambda *, port=None, cache_dir=None: _fake_runtime())
    )
    results = _by_name(_run_checks())
    assert results["agent-api"].ok
    assert "0.2.0" in results["agent-api"].detail


def test_runtime_without_credentials_fails_with_fixit(holo_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAI_API_KEY", "key")
    monkeypatch.setattr(
        doctor.LocalRuntime,
        "attach",
        staticmethod(lambda *, port=None, cache_dir=None: _fake_runtime(api_key=None)),
    )
    results = _by_name(_run_checks())
    assert not results["agent-api"].ok
    assert results["agent-api"].fix is not None


def test_unhealthy_runtime_fails_and_points_at_force_stop(holo_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAI_API_KEY", "key")
    monkeypatch.setattr(
        doctor.LocalRuntime,
        "attach",
        staticmethod(lambda *, port=None, cache_dir=None: _fake_runtime(healthy=False)),
    )
    results = _by_name(_run_checks())
    assert not results["agent-api"].ok
    assert "holo stop --force" in (results["agent-api"].fix or "")


@pytest.mark.skipif(sys.platform != "darwin", reason="TCC guidance is macOS-only")
def test_permissions_guidance_shown_while_managed_first_run_pending(holo_home: Path) -> None:
    # No first-run marker and no `hai-agent-runtime` on PATH: grants were almost certainly never given.
    assert doctor.permissions_guidance_needed(18795)


@pytest.mark.skipif(sys.platform != "darwin", reason="TCC guidance is macOS-only")
def test_permissions_guidance_hidden_after_first_run_completes(holo_home: Path) -> None:
    permissions.mark_first_run_complete()
    assert not doctor.permissions_guidance_needed(18795)


@pytest.mark.skipif(sys.platform != "darwin", reason="TCC guidance is macOS-only")
def test_permissions_guidance_reappears_on_permission_shaped_log(
    holo_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    permissions.mark_first_run_complete()
    log = holo_home / "logs" / "runtime.log"
    log.parent.mkdir()
    log.write_text("screen recording denied by TCC\n", encoding="utf-8")
    runtime = _fake_runtime()
    runtime.log_path = log
    monkeypatch.setattr(doctor.LocalRuntime, "attach", staticmethod(lambda *, port=None, cache_dir=None: runtime))
    assert doctor.permissions_guidance_needed(18795)


@pytest.mark.skipif(sys.platform != "darwin", reason="TCC guidance is macOS-only")
def test_permissions_guidance_hidden_for_path_binary(holo_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # A dev binary on PATH never gets a first-run marker; without this gate the panel would show forever.
    bin_dir = holo_home / "bin"
    bin_dir.mkdir()
    binary = bin_dir / "hai-agent-runtime"
    binary.write_bytes(b"#!/bin/sh\n")
    binary.chmod(0o755)
    monkeypatch.setenv("PATH", str(bin_dir))
    assert not doctor.permissions_guidance_needed(18795)


@pytest.mark.skipif(sys.platform == "darwin", reason="covers the non-macOS branch")
def test_permissions_guidance_never_shown_off_macos(holo_home: Path) -> None:
    assert not doctor.permissions_guidance_needed(18795)


@pytest.mark.skipif(sys.platform != "darwin", reason="TCC guidance is macOS-only")
def test_doctor_output_omits_permissions_panel_when_healthy(
    holo_home: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("HAI_API_KEY", "key")
    _seed_skill(holo_home)
    permissions.mark_first_run_complete()
    monkeypatch.setattr(
        doctor.LocalRuntime, "attach", staticmethod(lambda *, port=None, cache_dir=None: _fake_runtime())
    )
    doctor.doctor()
    assert "macOS permissions" not in capsys.readouterr().out


def test_doctor_exit_codes(holo_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(SystemExit) as excinfo:
        doctor.doctor()
    assert excinfo.value.code == 1

    monkeypatch.setenv("HAI_API_KEY", "key")
    _seed_skill(holo_home)
    monkeypatch.setattr(
        doctor.LocalRuntime, "attach", staticmethod(lambda *, port=None, cache_dir=None: _fake_runtime())
    )
    doctor.doctor()  # all green: returns normally (exit 0)
