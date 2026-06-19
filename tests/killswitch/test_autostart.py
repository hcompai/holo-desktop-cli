"""Guard autostart renders the right per-OS artifact and writes it idempotently."""

from __future__ import annotations

from pathlib import Path

import pytest

from holo_desktop.killswitch import autostart
from holo_desktop.killswitch.autostart import (
    AutostartResult,
    ensure_autostart,
    render_linux_desktop,
    render_macos_plist,
    render_windows_launcher,
)


def test_macos_plist_runs_holo_guard_with_load_flags() -> None:
    plist = render_macos_plist("/opt/holo/bin/holo", Path("/tmp/holo-guard.log"))
    assert "<string>/opt/holo/bin/holo</string>" in plist
    assert "<string>guard</string>" in plist
    assert "<key>RunAtLoad</key>\n    <true/>" in plist
    assert "<key>KeepAlive</key>\n    <true/>" in plist
    assert "ai.hcompany.holo.guard" in plist


def test_windows_launcher_starts_holo_guard_detached() -> None:
    assert render_windows_launcher("C:\\holo\\holo.exe") == '@echo off\r\nstart "" "C:\\holo\\holo.exe" guard\r\n'


def test_linux_desktop_execs_holo_guard() -> None:
    desktop = render_linux_desktop("/usr/bin/holo")
    assert "Exec=/usr/bin/holo guard" in desktop
    assert "Type=Application" in desktop


def test_ensure_macos_writes_then_skips(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(autostart.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(autostart, "LAUNCH_AGENTS_DIR", tmp_path / "LaunchAgents")
    monkeypatch.setattr(autostart, "GUARD_LOG_PATH", tmp_path / "logs" / "holo-guard.log")
    monkeypatch.setattr(autostart.os, "getuid", lambda: 501, raising=False)
    activations: list[list[str]] = []
    monkeypatch.setattr(autostart, "_run_quietly", lambda cmd: activations.append(cmd))

    result, detail = ensure_autostart("/opt/holo/bin/holo")
    assert result is AutostartResult.INSTALLED
    plist = Path(detail)
    assert plist.exists()
    assert "holo" in plist.read_text(encoding="utf-8")
    assert any("bootstrap" in part for cmd in activations for part in cmd)

    again, _ = ensure_autostart("/opt/holo/bin/holo")
    assert again is AutostartResult.SKIPPED


def test_wayland_is_unsupported(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(autostart.platform, "system", lambda: "Linux")
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    result, _ = ensure_autostart("/usr/bin/holo")
    assert result is AutostartResult.UNSUPPORTED


def test_ensure_loaded_is_noop_when_not_installed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(autostart.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(autostart, "LAUNCH_AGENTS_DIR", tmp_path / "LaunchAgents")
    monkeypatch.setattr(autostart.os, "getuid", lambda: 501, raising=False)
    calls: list[list[str]] = []
    monkeypatch.setattr(autostart, "_run_quietly", lambda cmd: calls.append(cmd))

    autostart.ensure_loaded()

    assert calls == []


def test_ensure_loaded_bootstraps_an_installed_guard(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    agents = tmp_path / "LaunchAgents"
    agents.mkdir(parents=True)
    (agents / "ai.hcompany.holo.guard.plist").write_text("x", encoding="utf-8")
    monkeypatch.setattr(autostart.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(autostart, "LAUNCH_AGENTS_DIR", agents)
    monkeypatch.setattr(autostart.os, "getuid", lambda: 501, raising=False)
    calls: list[list[str]] = []
    monkeypatch.setattr(autostart, "_run_quietly", lambda cmd: calls.append(cmd))

    autostart.ensure_loaded()

    assert any("bootstrap" in part for cmd in calls for part in cmd)
